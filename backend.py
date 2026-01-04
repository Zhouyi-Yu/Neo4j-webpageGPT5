"""
tryGPT5_v2.py  —  new multi-stage LLM wiring (FASTAPI ASYNC VERSION)

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
from openai import AsyncOpenAI
from neo4j import AsyncGraphDatabase
import asyncio
import time

# ───────────────────────────────────────────────────────────────
# LOAD ENV (.env in this folder)
# ───────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Use override=True and explicit strip to ensure .env takes precedence
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

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

MIN_RELEVANCE_SCORE = 0.7  # Increased from 0.65 to reduce noise

OPENAI_MODEL_CHAT = "gpt-4o-mini"                     # gpt-5-mini is not available, using standard chat model
OPENAI_MODEL_EMBED = "text-embedding-3-large"     # embedding model

# Neo4j connection
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

# Async OpenAI client
api_key = os.getenv("OPENAI_API_KEY", "").strip()
client = AsyncOpenAI(api_key=api_key)

# Async Neo4j driver
driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ───────────────────────────────────────────────────────────────
# LLM HELPER
# ───────────────────────────────────────────────────────────────

async def call_llm(system_prompt: str, user_content: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> str:
    """
    LLM call using the Chat Completions API with optional conversation history.
    Restored logic parity with olderVer but using Async and ChatCompletions.
    """
    # Build input messages: system + history + current user message
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history if provided (limit to last 5 exchanges to prevent context overflow)
    if conversation_history:
        # Take last 10 messages (5 Q&A pairs)
        recent_history = conversation_history[-10:]
        messages.extend(recent_history)
    
    # Add current user message
    messages.append({"role": "user", "content": user_content})
    
    resp = await client.chat.completions.create(
        model=OPENAI_MODEL_CHAT,
        messages=messages,
    )

    content = resp.choices[0].message.content
    if content:
        return content.strip()

    # If we got here, something is wrong with the response shape
    raise RuntimeError("LLM response had no message text output")



# ───────────────────────────────────────────────────────────────
# STEP 1: INTENT CLASSIFICATION
# ───────────────────────────────────────────────────────────────

async def classify_intent(question: str) -> Dict[str, Any]:
    raw = await call_llm(INTENT_SYSTEM_PROMPT, question)
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

async def generate_cypher(intent_obj: Dict[str, Any]) -> str:
    """
    Send the full intent (including fields like authorUserId)
    to the Cypher-generator model.
    """
    cypher_context = intent_obj  # includes authorUserId if resolve_author set it
    user_content = json.dumps(cypher_context, ensure_ascii=False)
    cypher = await call_llm(CYPHER_SYSTEM_PROMPT, user_content)
    return cypher.strip()


async def generate_author_cypher(semantic_hits: List[Dict[str, Any]]) -> str:
    """
    Generate Cypher to find authors for the given semantic hits.
    RESTORED: Using LLM to generate Cypher as in olderVer.
    """
    titles = [hit.get("title") for hit in semantic_hits if hit.get("title")]
    if not titles:
        return ""
    
    # Pass the titles context to the LLM so it understands what we are looking for,
    # even though the prompt instructs to use the $titles parameter.
    user_content = f"Here is the list of titles to find authors for: {json.dumps(titles)}"
    cypher = await call_llm(AUTHOR_DISCOVERY_PROMPT, user_content)
    
    # Clean up markdown code blocks if present
    cypher = cypher.replace("```cypher", "").replace("```", "").strip()
    return cypher



# ───────────────────────────────────────────────────────────────
# NEO4J HELPERS
# ───────────────────────────────────────────────────────────────

async def run_cypher(cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    params = params or {}
    async with driver.session() as session:
        result = await session.run(cypher, **params)
        records = await result.data()
        return records


async def recursive_semantic_answer(
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
    return await call_llm(SEMANTIC_REASK_PROMPT, user_content)

async def resolve_author(intent_obj: Dict[str, Any]) -> tuple:
    """
    Resolves author name to a specific userId.
    Returns: (updated_intent, candidates_if_any, metadata)
    """
    author_name = (intent_obj.get("author") or "").strip()
    if not author_name:
        return intent_obj, None, {"resolution_path": "NONE"}

    async with driver.session() as session:
        # Step 1: Exact Match (Case-Insensitive)
        exact_cypher = """
        MATCH (r:Researcher)
        WHERE (toLower(r.name) = toLower($name) OR toLower(r.normalized_name) = toLower($name))
          AND (r.userId IS NOT NULL OR r.ccid IS NOT NULL)
        RETURN r.userId AS userId, coalesce(r.name, r.normalized_name) AS name, r.normalized_name AS normalized_name
        ORDER BY r.name DESC
        LIMIT 1
        """
        result = await session.run(exact_cypher, name=author_name)
        exact_result = await result.single()
        
        if exact_result:
            # Exact match found
            intent_obj["author"] = exact_result["name"]
            intent_obj["authorUserId"] = exact_result["userId"]
            return intent_obj, None, {"resolution_path": "EXACT"}

        # Step 2: Fuzzy Search Fallback
        # RESTORED: Fuzzy search should NOT auto-select unless extremely confident
        # Actually, for the demo, we want to see the selection list if it's not an exact match.
        if " " in author_name:
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
        result = await session.run(fuzzy_cypher, term=fuzzy_name_query)
        rows = await result.data()

        # Metadata for telemetry
        metadata = {
            "resolution_path": "FUZZY",
            "fuzzy_scores": [r.get("score", 0) for r in rows]
        }

        # If fuzzy returns matches, treat them as candidates (no auto-select here)
        if rows:
            return intent_obj, rows, metadata

        return intent_obj, None, metadata



# ───────────────────────────────────────────────────────────────
# SEMANTIC SEARCH (VECTOR INDEX)
# ───────────────────────────────────────────────────────────────

async def get_embedding(text: str) -> List[float]:
    """
    Get an embedding vector for the topic string.
    """
    if not text:
        return []
    resp = await client.embeddings.create(
        model=OPENAI_MODEL_EMBED,
        input=text,
    )
    return resp.data[0].embedding  # type: ignore[attr-defined]

async def semantic_search_publications(topic: Optional[str], k: int = 200) -> List[Dict[str, Any]]:
    """
    Use Neo4j vector index on Publication.embedding.
    Assumes VECTOR_INDEX_NAME exists on :Publication(embedding).
    If the index is missing or misconfigured, this will log the error
    and return an empty list instead of crashing the whole request.
    """
    if not topic:
        return []

    embedding = await get_embedding(topic)
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
        async with driver.session() as session:
            result = await session.run(cypher, k=k, embedding=embedding)
            records = await result.data()
            return records
    except Exception as e:
        # Don't turn vector-index issues into HTTP 500s.
        # They will still show up in your Flask logs.
        print(f"[semantic_search_publications] Error during vector query: {e}")
        return []


async def _semantic_search_with_embedding(embedding: List[float], k: int = 20) -> List[Dict[str, Any]]:
    """Helper for Step 0 optimization."""
    if not embedding: return []
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
           node.abstract         AS abstract,
           node.openalex_url     AS openalex_url,
           node.doi              AS doi,
           score
    ORDER BY score DESC
    LIMIT $k
    """
    try:
        async with driver.session() as session:
            result = await session.run(cypher, k=k, embedding=embedding)
            return await result.data()
    except Exception as e:
        print(f"[semantic_search_uofa] Error: {e}")
        return []

async def semantic_search_uofa(question_text: str, k: int = 20) -> List[Dict[str, Any]]:
    """
    Fallback semantic search that only returns publications authored by
    University of Alberta people (detected via Person nodes with ccid/userId).
    Returns the limited fields requested: title, publication_year, score, cited_by_count.
    """
    if not question_text:
        return []

    embedding = await get_embedding(question_text)
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
           node.abstract         AS abstract,
           node.openalex_url     AS openalex_url,
           node.doi              AS doi,
           score
    ORDER BY score DESC
    LIMIT $k
    """

    try:
        async with driver.session() as session:
            result = await session.run(cypher, k=k, embedding=embedding)
            records = await result.data()
            return records
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

async def synthesize_answer(
    question: str,
    intent_obj: Dict[str, Any],
    cypher: str,
    db_rows: List[Dict[str, Any]],
    semantic_hits: List[Dict[str, Any]],
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    payload = {
        "question": question,
        "intent": intent_obj,
        "cypher": cypher,
        "db_rows": _sanitize_payload(db_rows),
        "semantic_hits": _sanitize_payload(semantic_hits),
    }
    user_content = json.dumps(payload, ensure_ascii=False)
    answer = await call_llm(ANSWER_SYSTEM_PROMPT, user_content, conversation_history)
    return answer.strip()


async def synthesize_final_author_answer(
    question: str,
    semantic_hits: List[Dict[str, Any]],
    author_rows: List[Dict[str, Any]],
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    payload = {
        "question": question,
        "semantic_hits": _sanitize_payload(semantic_hits),
        "author_data": _sanitize_payload(author_rows),
    }
    user_content = json.dumps(payload, ensure_ascii=False)
    return (await call_llm(FINAL_AUTHOR_ANSWER_PROMPT, user_content, conversation_history)).strip()


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
    CRITICAL: For author-based intents, we now REQUIRE authorUserId (the ID).
    """
    intent = (intent_obj or {}).get("intent")
    if intent in AUTHOR_INTENTS_REQUIRING_AUTHOR:
        if not (intent_obj or {}).get("authorUserId"):
            return False
    if intent == "AUTHOR_PAIR_SHARED_PUBLICATIONS":
        # Note: shared publications usually takes IDs too, but we haven't fully expanded it yet
        if not ((intent_obj or {}).get("authorUserId") and (intent_obj or {}).get("second_author")):
            return False
    if intent == "DEPARTMENT_TOPIC_TRENDS":
        if not (intent_obj or {}).get("department"):
            return False
    return True

async def answer_question(question: str, conversation_history: Optional[List[Dict[str, str]]] = None, selected_user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Full pipeline (ASYNC VERSION): Matches the exact logic and flow of olderVer/backend.py.
    """
    result = {
        "answer": "An internal error occurred while processing your request.",
        "intent": {},
        "cypher": "",
        "dbRows": [],
        "semanticHits": [],
        "telemetry": {
            "timings": {},
            "resolution": {}
        }
    }

    try:
        total_start = time.perf_counter()

        # ~~~ STEP 0 & 1: INTENT & EMBEDDING (SPECULATIVE PARALLEL) ~~~
        # We run classification and embedding generation for the fallback concurrently
        step0_start = time.perf_counter()
        intent_task = asyncio.create_task(classify_intent(question))
        embedding_task = asyncio.create_task(get_embedding(question))
        
        intent_obj, question_embedding = await asyncio.gather(intent_task, embedding_task)
        result["telemetry"]["timings"]["step0_setup"] = round(time.perf_counter() - step0_start, 3)

        intent_obj = normalize_intent(intent_obj)
        result["intent"] = intent_obj

        # ~~~ STEP 3: AUTHOR RESOLUTION & INTENT PROMOTION ~~~
        # Skip resolution if we already have a direct user selection (ID)
        author_to_check = intent_obj.get("author")
        
        if author_to_check and not selected_user_id:
            res_start = time.perf_counter()
            
            # If classifier didn't find specific author, try forceful extraction
            if not author_to_check:
                try:
                    extracted = (await call_llm(NAME_EXTRACTION_PROMPT, question)).strip()
                    if extracted and len(extracted) > 3: 
                        author_to_check = extracted
                except Exception as e:
                    print(f"Name extraction failed: {e}")

            if author_to_check:
                temp_intent = dict(intent_obj)
                temp_intent["author"] = author_to_check
                
                updated_intent, candidates, res_meta = await resolve_author(temp_intent)
                result["telemetry"]["resolution"] = res_meta
                result["telemetry"]["timings"]["author_resolution"] = round(time.perf_counter() - res_start, 3)

                # If ANY candidates were found via fuzzy search, show the menu
                if candidates:
                     result["answer"] = (
                        f"I couldn't find exact matches for '{author_to_check}', "
                        "but I found similar researchers. Please select one:"
                    )
                     result["candidates"] = candidates
                     return result
                
                elif updated_intent.get("authorUserId"):
                    intent_obj["author"] = updated_intent["author"]
                    intent_obj["authorUserId"] = updated_intent["authorUserId"]
                    
                    if intent_obj.get("intent") == "OPEN_QUESTION":
                        intent_obj["intent"] = "AUTHOR_PUBLICATIONS_RANGE"
        
        elif selected_user_id:
            # Step 2: HANDLE DIRECT USER SELECTION
            # We already have the user selection from the frontend
            intent_obj["authorUserId"] = selected_user_id
            
            # Fetch the canonical name so the LLM doesn't use the typo from the original question
            async with driver.session() as session:
                name_query = "MATCH (p:Person {userId: $uid}) RETURN coalesce(p.name, p.normalized_name) AS name"
                name_res = await session.run(name_query, uid=selected_user_id)
                name_record = await name_res.single()
                if name_record:
                    intent_obj["author"] = name_record["name"]

            # Promote intent if it was too generic
            if intent_obj.get("intent") == "OPEN_QUESTION":
                intent_obj["intent"] = "AUTHOR_MAIN_RESEARCH_AREAS"

        # ~~~ STEP 4: BRANCHING LOGIC ~~~

        if is_template_intent(intent_obj) and has_required_slots(intent_obj):
            # Branch A: Structured Template Flow
            spec_start = time.perf_counter()
            cypher_task = asyncio.create_task(generate_cypher(intent_obj))
            
            semantic_hits = []
            if intent_obj.get("intent") in TOPIC_INTENTS:
                semantic_task = asyncio.create_task(semantic_search_publications(intent_obj.get("topic")))
                cypher, raw_hits = await asyncio.gather(cypher_task, semantic_task)
                semantic_hits = [h for h in raw_hits if h.get("score", 0) >= MIN_RELEVANCE_SCORE]
            else:
                cypher = await cypher_task
            
            result["telemetry"]["timings"]["speculative_generation"] = round(time.perf_counter() - spec_start, 3)
            result["cypher"] = cypher
            
            db_start = time.perf_counter()
            db_rows = await run_cypher(cypher)
            result["telemetry"]["timings"]["db_query"] = round(time.perf_counter() - db_start, 3)
            
            result["dbRows"] = db_rows
            result["semanticHits"] = semantic_hits

            # If no results from structured, try semantic fallback
            if not db_rows and not semantic_hits:
                fall_start = time.perf_counter()
                semantic_hits = await _semantic_search_with_embedding(question_embedding)
                result["telemetry"]["timings"]["semantic_fallback"] = round(time.perf_counter() - fall_start, 3)
                result["semanticHits"] = semantic_hits

            # Synthesize final answer
            syn_start = time.perf_counter()
            answer_text = await synthesize_answer(
                question=question,
                intent_obj=intent_obj,
                cypher=cypher,
                db_rows=db_rows,
                semantic_hits=semantic_hits,
                conversation_history=conversation_history
            )
            result["telemetry"]["timings"]["synthesis"] = round(time.perf_counter() - syn_start, 3)
            
            # Additional semantic pass if structured results were empty
            if not db_rows and semantic_hits:
                 try:
                    answer_text = await recursive_semantic_answer(question, semantic_hits, answer_text)
                 except: pass

            result["answer"] = answer_text

        else:
            # Branch B: Open Question / Semantic Flow
            open_start = time.perf_counter()
            sem_hits = await _semantic_search_with_embedding(question_embedding)
            result["semanticHits"] = sem_hits
            
            if not sem_hits:
                result["answer"] = (
                    "I could not find any relevant UAlberta publications or researchers matching your question with high confidence.\n\n"
                    "**Suggestions:**\n"
                    "- Try asking about specific engineering topics like 'smart grids', 'reinforcement learning', or 'nanotechnology'.\n"
                    "- Ask about specific University of Alberta researchers or departments.\n"
                    "- Ensure you are asking about work specifically within the Faculty of Engineering."
                )
                result["telemetry"]["timings"]["open_question"] = round(time.perf_counter() - open_start, 3)
                return result

            # Attempt a "Discovery" pass (look for authors of these papers)
            disc_start = time.perf_counter()
            author_cypher = await generate_author_cypher(sem_hits)
            result["cypher"] = author_cypher
            
            titles = [hit.get("title") for hit in sem_hits if hit.get("title")]
            author_rows = await run_cypher(author_cypher, params={"titles": titles})
            result["telemetry"]["timings"]["author_discovery"] = round(time.perf_counter() - disc_start, 3)
            result["dbRows"] = author_rows

            syn_start = time.perf_counter()
            final_answer = await synthesize_final_author_answer(question, sem_hits, author_rows, conversation_history)
            result["telemetry"]["timings"]["synthesis"] = round(time.perf_counter() - syn_start, 3)
            result["answer"] = final_answer
            result["telemetry"]["timings"]["open_question_pipeline"] = round(time.perf_counter() - open_start, 3)

        result["telemetry"]["timings"]["total"] = round(time.perf_counter() - total_start, 3)
        return result

    except Exception as e:
        print(f"Error in answer_question pipeline: {e}")
        import traceback
        traceback.print_exc()
        result["error"] = str(e)
        return result

# ───────────────────────────────────────────────────────────────
# CLI TEST (optional)
# ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def main():
        q = input("Ask a question about UAlberta research: ")
        result = await answer_question(q)
        print("\n=== Answer ===")
        print(result["answer"])
        print("\n=== Intent ===")
        print(json.dumps(result["intent"], indent=2))
        print("\n=== Cypher ===")
        print(result["cypher"])
    
    asyncio.run(main())
