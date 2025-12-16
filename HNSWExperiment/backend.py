"""
tryGPT5_v2.py  —  new multi-stage LLM wiring

Pipeline:
  1) classify_intent(question)  -> JSON
  2) generate_cypher(intent)    -> Cypher string
  3) run_cypher(cypher)         -> DB rows
  4) semantic_search_publications(topic) (for topic-y intents)
  5) synthesize_answer(...)     -> final text answer

Exported function:
  answer_question(question: str) -> dict
"""
import json
import os
from typing import Any, Dict, List, Optional, Set, Union

from dotenv import load_dotenv
from openai import OpenAI
from neo4j import GraphDatabase

# ───────────────────────────────────────────────────────────────
# LOAD ENV (.env in this folder)
# ───────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)

# ───────────────────────────────────────────────────────────────
# PROMPT LOADER
# ───────────────────────────────────────────────────────────────

def load_prompt(filename: str) -> str:
    """Load a prompt text file from HNSWExperiment/prompts."""
    prompt_path = os.path.join(BASE_DIR, "prompts", filename)
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

INTENT_SYSTEM_PROMPT = load_prompt("intent_prompt.txt")
CYPHER_SYSTEM_PROMPT = load_prompt("cypher_prompt.txt")
ANSWER_SYSTEM_PROMPT = load_prompt("answer_prompt.txt")
AUTHOR_DISCOVERY_PROMPT = load_prompt("author_discovery_prompt.txt")
FINAL_AUTHOR_ANSWER_PROMPT = load_prompt("final_author_answer_prompt.txt")

SEMANTIC_REASK_PROMPT = """
You are a second-pass assistant. Your inputs are:
- original user question
- semantic_hits: a list of publications (title, publication_year, cited_by_count, score)
- first_pass_summary: the initial answer we showed the user

Task:
- Re-answer the original question using the semantic_hits as evidence.
- If hits clearly point to relevant UAlberta work, provide a concise answer rooted in those hits.
- If evidence is still insufficient to answer for UAlberta authors, say so briefly (no embellishment).
- Keep the response under ~120 words and do not mention “semantic search” or internal steps.
"""

NAME_EXTRACTION_PROMPT = """
You are a helper that extracts person names from a user question.
If the question mentions a researcher, author, or person name, extract it.
Return ONLY the name. If no name is found, return nothing (empty string).
Do not explain.
Example 1: "Papers by Marek Reformat" -> Marek Reformat
Example 2: "tell me about reinforcement learning" -> 
Example 3: "who is witold pedrycz" -> Witold Pedrycz
"""


# ───────────────────────────────────────────────────────────────
# CONFIGURATION
# ───────────────────────────────────────────────────────────────

OPENAI_MODEL_CHAT = "gpt-5-mini"                     # pick your preferred chat model
OPENAI_MODEL_EMBED = "text-embedding-3-large"     # embedding model

# Neo4j connection (still hard-coded for now; you can env-ify later)
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# Vector index name for Publication.embedding
VECTOR_INDEX_NAME = "pub_embedding_index"  # TODO: match your CREATE VECTOR INDEX

# -------------------------------------------------------------------
# DEPARTMENT NORMALIZATION (handles "UAlberta Engineering" umbrella)
# -------------------------------------------------------------------

ENGINEERING_ALIASES: Set[str] = {
    "engineering",
    "uofa engineering",
    "ualberta engineering",
    "faculty of engineering",
    "faculty engineering",
    "engg",
}

ENGINEERING_DEPARTMENTS: List[str] = [
    "Electrical and Computer Engineering",
    "Mechanical Engineering",
    "Civil and Environmental Engineering",
    "Chemical and Materials Engineering",
    "Biomedical Engineering",
]


def _normalize_department_value(dept: Optional[Union[str, List[str]]]) -> Optional[Union[str, List[str]]]:
    """
    Expand umbrella department values like "Engineering" into a list of
    concrete Engineering departments.

    - If dept is already a list, return it unchanged.
    - If dept is a non-Engineering string, return it unchanged.
    - If dept is an Engineering umbrella, return ENGINEERING_DEPARTMENTS.
    """
    if dept is None:
        return None

    # If JSON already had a list, assume it's explicit and keep it
    if isinstance(dept, list):
        return dept

    if not isinstance(dept, str):
        return dept

    norm = dept.strip().lower()
    if norm in ENGINEERING_ALIASES:
        # return a copy so callers can't accidentally mutate the constant
        return ENGINEERING_DEPARTMENTS.copy()

    return dept


def normalize_intent(intent_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Post-process the raw intent JSON from the classifier.

    Currently:
      - Expands 'Engineering' / 'UAlberta Engineering' etc. into a list of
        concrete department names so the Cypher model can UNWIND them.

    This keeps all other fields identical.
    """
    normalized = dict(intent_obj)  # shallow copy
    normalized["department"] = _normalize_department_value(intent_obj.get("department"))
    return normalized

# OpenAI client reads OPENAI_API_KEY from env automatically
client = OpenAI()

# Neo4j driver
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ───────────────────────────────────────────────────────────────
# LLM HELPER
# ───────────────────────────────────────────────────────────────

def call_llm(system_prompt: str, user_content: str) -> str:
    """
    Single-turn LLM call using the Responses API.

    We ignore 'reasoning' items and extract text from the first 'message' item:
      - item.type == "message"
      - item.content[*].type == "output_text"
      - part.text can be either a plain string or an object with .value
    """
    resp = client.responses.create(
        model=OPENAI_MODEL_CHAT,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )

    for item in resp.output:
        if getattr(item, "type", None) == "message":
            text_chunks: List[str] = []
            for part in getattr(item, "content", []):
                if getattr(part, "type", None) == "output_text":
                    txt = getattr(part, "text", None)
                    # txt can be a plain string or an object with .value
                    if isinstance(txt, str):
                        text_chunks.append(txt)
                    elif txt is not None:
                        val = getattr(txt, "value", None)
                        if val is None and isinstance(txt, dict):
                            val = txt.get("value")
                        if isinstance(val, str):
                            text_chunks.append(val)
            if text_chunks:
                return "".join(text_chunks).strip()

    # If we got here, something is wrong with the response shape
    raise RuntimeError("LLM response had no message text output")



# ───────────────────────────────────────────────────────────────
# STEP 1: INTENT CLASSIFICATION
# ───────────────────────────────────────────────────────────────

def classify_intent(question: str) -> Dict[str, Any]:
    raw = call_llm(INTENT_SYSTEM_PROMPT, question)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback safe default
        obj = {
            "intent": "OPEN_QUESTION",
            "author": None,
            "second_author": None,
            "topic": None,
            "department": None,
            "start_year": None,
            "end_year": None,
            "scope": None,
        }
    # Ensure all keys exist
    for key in [
        "intent", "author", "second_author",
        "topic", "department",
        "start_year", "end_year", "scope"
    ]:
        obj.setdefault(key, None)
    return obj

# ───────────────────────────────────────────────────────────────
# STEP 2: CYPHER GENERATION
# ───────────────────────────────────────────────────────────────

def generate_cypher(intent_obj: Dict[str, Any]) -> str:
    """
    Send the full intent (including fields like authorUserId)
    to the Cypher-generator model.
    """
    cypher_context = intent_obj  # includes authorUserId if resolve_author set it
    user_content = json.dumps(cypher_context, ensure_ascii=False)
    cypher = call_llm(CYPHER_SYSTEM_PROMPT, user_content)
    return cypher.strip()


def generate_author_cypher(semantic_hits: List[Dict[str, Any]]) -> str:
    """
    Generate Cypher to find authors for the given semantic hits.
    """
    titles = [hit.get("title") for hit in semantic_hits if hit.get("title")]
    if not titles:
        return ""
    
    # Pass the titles context to the LLM so it understands what we are looking for,
    # even though the prompt instructs to use the $titles parameter.
    user_content = f"Here is the list of titles to find authors for: {json.dumps(titles)}"
    cypher = call_llm(AUTHOR_DISCOVERY_PROMPT, user_content)
    
    # Clean up markdown code blocks if present
    cypher = cypher.replace("```cypher", "").replace("```", "").strip()
    return cypher



# ───────────────────────────────────────────────────────────────
# NEO4J HELPERS
# ───────────────────────────────────────────────────────────────

def run_cypher(cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    params = params or {}
    with driver.session() as session:
        result = session.run(cypher, **params)
        return [dict(r) for r in result]


def recursive_semantic_answer(
    question: str,
    semantic_hits: List[Dict[str, Any]],
    first_pass_summary: str,
) -> str:
    """
    Re-ask the LLM using semantic hits + original question + first summary.
    """
    payload = {
        "question": question,
        "semantic_hits": [{k: (v[:500] + "..." if isinstance(v, str) and len(v) > 500 else v) for k, v in hit.items()} for hit in semantic_hits[:15]],
        "first_pass_summary": first_pass_summary,
    }
    user_content = json.dumps(payload, ensure_ascii=False)
    return call_llm(SEMANTIC_REASK_PROMPT, user_content)
def resolve_author(intent_obj: Dict[str, Any]):
    author_name = (intent_obj or {}).get("author")
    if not author_name:
        return intent_obj, None

    with driver.session() as session:
        # Step 1: Exact Match (Case-Insensitive)
        exact_cypher = """
        MATCH (r:Researcher)
        WHERE (toLower(r.name) = toLower($name) OR toLower(r.normalized_name) = toLower($name))
          AND (r.userId IS NOT NULL OR r.ccid IS NOT NULL)
        RETURN r.userId AS userId, r.name AS name, r.normalized_name AS normalized_name
        LIMIT 1
        """
        exact_result = session.run(exact_cypher, name=author_name).single()
        
        if exact_result:
            # Exact match found - auto-select
            intent_obj["author"] = exact_result["name"]
            intent_obj["authorUserId"] = exact_result["userId"]
            return intent_obj, None

        # Step 2: Fuzzy Search Fallback
        # Only runs if no exact match found

        # "Marek Reformat" -> "Marek~ Reformat~"
        # We split by space and append ~, then join.
        # Sanitization: fail safe if name is weird.
        if " " in author_name:
            # We want AND behavior usually? Or OR?
            # Lucene default is OR usually, but let's try just appending ~ to each term.
            # "TestMark~ Refamt~"
            fuzzy_name_query = " ".join([f"{part}~" for part in author_name.split() if part.strip()])
        else:
            fuzzy_name_query = author_name + "~"

        fuzzy_cypher = """
        CALL db.index.fulltext.queryNodes("researcher_name_index", $term) YIELD node, score
        WHERE (node.userId IS NOT NULL OR node.ccid IS NOT NULL)
        OPTIONAL MATCH (node)-[:BELONGS_TO]->(d:Department)
        RETURN node.userId AS userId,
               coalesce(node.name, node.normalized_name) AS name,
               node.normalized_name AS normalized_name,
               collect(DISTINCT d.department) AS departments,
               score
        ORDER BY score DESC
        LIMIT 5
        """
        rows = [dict(r) for r in session.run(fuzzy_cypher, term=fuzzy_name_query)]

        # If fuzzy returns matches, treat them as candidates
        if rows:
            return intent_obj, rows

        # If no results at all, return None
        return intent_obj, None



# ───────────────────────────────────────────────────────────────
# SEMANTIC SEARCH (VECTOR INDEX)
# ───────────────────────────────────────────────────────────────

def get_embedding(text: str) -> List[float]:
    """
    Get an embedding vector for the topic string.
    """
    if not text:
        return []
    resp = client.embeddings.create(
        model=OPENAI_MODEL_EMBED,
        input=text,
    )
    return resp.data[0].embedding  # type: ignore[attr-defined]

def semantic_search_publications(topic: Optional[str], k: int = 200) -> List[Dict[str, Any]]:
    """
    Use Neo4j vector index on Publication.embedding.
    Assumes VECTOR_INDEX_NAME exists on :Publication(embedding).
    If the index is missing or misconfigured, this will log the error
    and return an empty list instead of crashing the whole request.
    """
    if not topic:
        return []

    embedding = get_embedding(topic)
    if not embedding:
        return []

    cypher = f"""
    CALL db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', $k, $embedding)
    YIELD node, score
    RETURN node.openalex_url        AS openalex_url,
           node.title               AS title,
           node.abstract            AS abstract,
           node.publication_year    AS publication_year,
           score
    """

    try:
        with driver.session() as session:
            result = session.run(cypher, k=k, embedding=embedding)
            return [dict(r) for r in result]
    except Exception as e:
        # Don't turn vector-index issues into HTTP 500s.
        # They will still show up in your Flask logs.
        print(f"[semantic_search_publications] Error during vector query: {e}")
        return []


def semantic_search_uofa(question_text: str, k: int = 20) -> List[Dict[str, Any]]:
    """
    Fallback semantic search that only returns publications authored by
    University of Alberta people (detected via Person nodes with ccid/userId).
    Returns the limited fields requested: title, publication_year, score, cited_by_count.
    """
    if not question_text:
        return []

    embedding = get_embedding(question_text)
    if not embedding:
        return []

    cypher = f"""
    CALL db.index.vector.queryNodes('{VECTOR_INDEX_NAME}', $k, $embedding)
    YIELD node, score
    MATCH (node)<-[:PUBLISHED]-(ap:AuthorProfile)
    OPTIONAL MATCH (person:Person)-[:HAS_PROFILE {{source:'openalex'}}]->(ap)
    WITH node, score, person
    WHERE person IS NOT NULL AND (person.userId IS NOT NULL OR person.ccid IS NOT NULL)
    RETURN node.title            AS title,
           node.publication_year AS publication_year,
           coalesce(node.cited_by_count, 0) AS cited_by_count,
           score
    ORDER BY score DESC
    LIMIT $k
    """

    try:
        with driver.session() as session:
            result = session.run(cypher, k=k, embedding=embedding)
            return [dict(r) for r in result]
    except Exception as e:
        print(f"[semantic_search_uofa] Error during vector query: {e}")
        return []


# ───────────────────────────────────────────────────────────────
# STEP 3: ANSWER SYNTHESIS
# ───────────────────────────────────────────────────────────────

# ───────────────────────────────────────────────────────────────
# STEP 3: ANSWER SYNTHESIS
# ───────────────────────────────────────────────────────────────

def _sanitize_payload(data: Union[Dict, List], max_items: int = 15, max_text_len: int = 500) -> Union[Dict, List]:
    """
    Recursively sanitize data sent to LLM to prevent context window explosion.
    - Limits list length to `max_items`.
    - Truncates long string values (like 'abstract') to `max_text_len`.
    """
    if isinstance(data, list):
        # Limit list size
        sliced = data[:max_items]
        return [_sanitize_payload(item, max_items, max_text_len) for item in sliced]
    
    if isinstance(data, dict):
        new_dict = {}
        for k, v in data.items():
            if isinstance(v, str) and len(v) > max_text_len:
                new_dict[k] = v[:max_text_len] + "...(truncated)"
            elif isinstance(v, (dict, list)):
                new_dict[k] = _sanitize_payload(v, max_items, max_text_len)
            else:
                new_dict[k] = v
        return new_dict
    
    return data

def synthesize_answer(
    question: str,
    intent_obj: Dict[str, Any],
    cypher: str,
    db_rows: List[Dict[str, Any]],
    semantic_hits: List[Dict[str, Any]],
) -> str:
    payload = {
        "question": question,
        "intent": intent_obj,
        "cypher": cypher,
        "db_rows": _sanitize_payload(db_rows),
        "semantic_hits": _sanitize_payload(semantic_hits),
    }
    user_content = json.dumps(payload, ensure_ascii=False)
    answer = call_llm(ANSWER_SYSTEM_PROMPT, user_content)
    return answer.strip()


def synthesize_final_author_answer(
    question: str,
    semantic_hits: List[Dict[str, Any]],
    author_rows: List[Dict[str, Any]],
) -> str:
    payload = {
        "question": question,
        "semantic_hits": _sanitize_payload(semantic_hits),
        "author_data": _sanitize_payload(author_rows),
    }
    user_content = json.dumps(payload, ensure_ascii=False)
    return call_llm(FINAL_AUTHOR_ANSWER_PROMPT, user_content).strip()


# ───────────────────────────────────────────────────────────────
# TOP-LEVEL PIPELINE
# ───────────────────────────────────────────────────────────────

TOPIC_INTENTS: Set[str] = {
    "AUTHOR_TOPIC_PUBLICATION_COUNT",
    "AUTHOR_TOPIC_EXTENT",
    "AUTHOR_TOPIC_SYNERGY",
    "AUTHOR_TOPIC_PEERS_AT_UOFA",
    "DEPARTMENT_TOPIC_TRENDS",
}
TEMPLATE_INTENTS: Set[str] = {
    "AUTHOR_PUBLICATIONS_RANGE",
    "AUTHOR_LATEST_PUBLICATION",
    "AUTHOR_TOP_VENUE",
    "AUTHOR_PAIR_SHARED_PUBLICATIONS",
    "AUTHOR_TOP_COAUTHORS",
    "AUTHOR_TOPIC_PUBLICATION_COUNT",
    "AUTHOR_TOPIC_EXTENT",
    "AUTHOR_MAIN_RESEARCH_AREAS",
    "AUTHOR_TOPIC_SYNERGY",
    "AUTHOR_INSTITUTION_COLLAB_FREQUENCY",
    "AUTHOR_TOPIC_PEERS_AT_UOFA",
    "DEPARTMENT_TOPIC_TRENDS",
}
AUTHOR_INTENTS_REQUIRING_AUTHOR: Set[str] = TEMPLATE_INTENTS - {"DEPARTMENT_TOPIC_TRENDS"}


def is_template_intent(intent_obj: Dict[str, Any]) -> bool:
    """
    Return True when the classified intent maps to a known structured template.
    """
    return (intent_obj or {}).get("intent") in TEMPLATE_INTENTS


def has_required_slots(intent_obj: Dict[str, Any]) -> bool:
    """
    Ensure required slots are present before running template-based logic.
    """
    intent = (intent_obj or {}).get("intent")
    if intent in AUTHOR_INTENTS_REQUIRING_AUTHOR:
        if not (intent_obj or {}).get("author"):
            return False
    if intent == "AUTHOR_PAIR_SHARED_PUBLICATIONS":
        if not ((intent_obj or {}).get("author") and (intent_obj or {}).get("second_author")):
            return False
    if intent == "DEPARTMENT_TOPIC_TRENDS":
        if not (intent_obj or {}).get("department"):
            return False
    return True

def answer_question(question: str) -> Dict[str, Any]:
    """
    Full pipeline:
      1) classify intent
      2) resolve author name (disambiguation / candidate listing)
      3) generate cypher
      4) run cypher
      5) run semantic search if needed
      6) synthesize final answer

    Returns a dict suitable for jsonify in Flask.
    """
    intent_obj = classify_intent(question)

    # Branch 1: open / non-template questions → semantic-only fallback
    if not (is_template_intent(intent_obj) and has_required_slots(intent_obj)):
        intent_obj = normalize_intent(intent_obj)

        # ~~~ AUTHOR DISCOVERY & FUZZY CHECK ~~~
        # Even for open questions, if there's an author name (or we can extract one),
        # we should try to resolve it to catch typos ("Possible Candidates").
        author_to_check = intent_obj.get("author")
        
        # If classifier didn't find specific author, try forceful extraction
        if not author_to_check:
            try:
                # We only try extraction if the question is short-ish or likely to contain a name.
                # For safety, just try it.
                extracted = call_llm(NAME_EXTRACTION_PROMPT, question).strip()
                # Sanity: ignore common false positives or very short strings
                if extracted and len(extracted) > 3 and " " in extracted: 
                    author_to_check = extracted
            except Exception as e:
                print(f"Name extraction failed: {e}")
        
        if author_to_check:
            # Try to resolve/fuzzy match
            # We construct a temp intent just for resolution
            temp_intent = dict(intent_obj)
            temp_intent["author"] = author_to_check
            
            updated_intent, candidates = resolve_author(temp_intent)
            
            if candidates:
                msg = (
                    f"I couldn't find exact matches for '{author_to_check}', "
                    "but I found similar researchers. Please select one:"
                )
                return {
                    "answer": msg,
                    "intent": updated_intent,
                    "cypher": "",
                    "dbRows": [],
                    "semanticHits": [],
                    "candidates": candidates,
                }
            
            # If exact match found (candidates=None, but userId set), we can use it!
            if updated_intent.get("authorUserId"):
                intent_obj["author"] = updated_intent["author"]
                intent_obj["authorUserId"] = updated_intent["authorUserId"]
                # We could behave like a standard Author query now, but let's stick to semantic fallback
                # but with the CORRECT name.

        # ~~~ END AUTHOR DISCOVERY ~~~
        
        # 1. Semantic Search (UAlberta authors only, limited fields)
        semantic_hits = semantic_search_uofa(question)
        
        if not semantic_hits:
            return {
                "answer": "I could not find any relevant UAlberta publications for your question.",
                "intent": intent_obj,
                "cypher": "",
                "dbRows": [],
                "semanticHits": [],
            }

        # 2. Generate Cypher to find authors for these specific publications
        author_cypher = generate_author_cypher(semantic_hits)
        
        # 3. Run Cypher (passing titles as parameter)
        titles = [hit.get("title") for hit in semantic_hits if hit.get("title")]
        try:
            author_rows = run_cypher(author_cypher, params={"titles": titles})
        except Exception as e:
            print(f"Error running author discovery cypher: {e}")
            author_rows = []

        # 4. Synthesize Final Answer using Semantic Hits + Author Data
        final_answer = synthesize_final_author_answer(question, semantic_hits, author_rows)

        return {
            "answer": final_answer,
            "intent": intent_obj,
            "cypher": author_cypher,
            "dbRows": author_rows,
            "semanticHits": semantic_hits,
        }

    # Branch 2: template-driven flow
    intent_obj = normalize_intent(intent_obj)

    # NEW STEP: resolve author; may return candidate list for ambiguous names
    intent_obj, author_candidates = resolve_author(intent_obj)
    intent_obj = normalize_intent(intent_obj)

    # If we have multiple candidates, short-circuit and ask the user to choose
    if author_candidates is not None and len(author_candidates) > 1:
        # Keep answer short; UI will show the candidate list
        typed_author = (intent_obj or {}).get("author")
        msg = (
            f"I found multiple researchers matching '{typed_author}'. "
            "Please pick the correct one from the list."
        )
        return {
            "answer": msg,
            "intent": intent_obj,
            "cypher": "",
            "dbRows": [],
            "semanticHits": [],
            "candidates": author_candidates,
        }

    # Normal flow (either no author, or resolved to a single researcher)
    cypher = generate_cypher(intent_obj)
    db_rows = run_cypher(cypher)

    if intent_obj.get("intent") in TOPIC_INTENTS:
        semantic_hits = semantic_search_publications(intent_obj.get("topic"))
    else:
        semantic_hits = []

    # If nothing came back from structured query and semantic hits are empty,
    # run the UAlberta-only semantic fallback using the original question.
    if not db_rows and not semantic_hits:
        semantic_hits = semantic_search_uofa(question)

    # 7) Synthesize final natural-language answer
    answer_text = synthesize_answer(
        question=question,
        intent_obj=intent_obj,
        cypher=cypher,
        db_rows=db_rows,
        semantic_hits=semantic_hits,
    )

    # If we still have no DB rows, run a second-pass answer using semantic hits (if any).
    if not db_rows and semantic_hits:
        answer_text = recursive_semantic_answer(question, semantic_hits, answer_text)

    # 8) Return full payload for the frontend
    return {
        "answer": answer_text,
        "intent": intent_obj,
        "cypher": cypher,
        "dbRows": db_rows,
        "semanticHits": semantic_hits,
    }

# ───────────────────────────────────────────────────────────────
# CLI TEST (optional)
# ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    q = input("Ask a question about UAlberta research: ")
    result = answer_question(q)
    print("\n=== Answer ===")
    print(result["answer"])
    print("\n=== Intent ===")
    print(json.dumps(result["intent"], indent=2))
    print("\n=== Cypher ===")
    print(result["cypher"])
