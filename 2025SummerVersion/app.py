from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import AsyncOpenAI
from neo4j import AsyncGraphDatabase
import logging, sys, asyncio, os, re, json
from datetime import datetime
from typing import List
from collections import Counter

# ─── Logging Setup ─────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# File handler (writes to log.txt)
fh = logging.FileHandler("log.txt", encoding="utf-8")
fh.setLevel(logging.INFO)

# Console handler (keeps printing to terminal)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)

# Common format
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
fh.setFormatter(formatter)
ch.setFormatter(formatter)

# Attach handlers
logger.addHandler(fh)
logger.addHandler(ch)

# Replace print with logger.info
print = logger.info

# ─── Configuration ───────────────────────────────────────────────────────────────
# Connection settings for Neo4j database and OpenAI model
NEO4J_URI = "bolt://129.128.218.235:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
MODEL_NAME = "gpt-4"

# Initialize clients
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", "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"))
driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

_TOKEN_RE = re.compile(r"^[a-zA-Z][a-zA-Z\-']{1,}$")
# ─── System Prompts ──────────────────────────────────────────────────────────────
# Prompt 1: Instructs AI to convert user questions into Cypher queries only
SYSTEM_PROMPT_1 = (
    "You are a Neo4j Cypher expert. Convert user questions into valid Cypher queries. "
    "Respond with only the Cypher query, no explanation. Follow these exact patterns:"
)

# Prompt 2: Defines database schema, relationships, and query patterns in detail
SYSTEM_PROMPT_2 = """
You are a Cypher query generator. You MUST strictly adhere to the provided schema and query patterns.
Do not invent node properties that are not listed in the schema. Do not deviate from the query patterns.

Database Schema:

Nodes:
- Researcher: {userId, ccid, firstName, lastName, email, rank, website, active, openalex_url, normalized_name, name}
- Department: {department, abbr}
- Publication: {openalex_url, doi, title, cited_by_count, cited_by_url, publication_year, volume, page}
- Keyword: {name}
- Tag: {name}
- Venue: {name, type}
- Institution: {name}

Please always use the following schema when generating Cypher queries:
Relationships:
- (Researcher)-[:BELONGS_TO]->(Department)-[:AFFILIATED_WITH_UNIVERSITY]->(Institution)
- (Researcher)-[:AFFILIATED_WITH]->(Institution)
- (Researcher)-[:PUBLISHED]->(Publication)
- (Researcher)-[:CO_AUTHOR_WITH]->(Researcher)
- (Researcher)-[:STUDIES]->(Tag)
- (Researcher)-[:WORKS_ON]->(Keyword)
- (Publication)-[:PUBLISHED_IN]->(Venue)

Abbreviations:
- ECE: Electrical and Computer Engineering


Query Patterns:

1. For "What did <Name> publish from <Year1>-<Year2> with co-authors":
WITH '<Name>' AS inputName, <Year1> AS startYear, <Year2> AS endYear
WITH toLower(inputName) AS normName, startYear, endYear
MATCH (r:Researcher {normalized_name: normName})-[:PUBLISHED]->(p:Publication)
WHERE p.publication_year >= startYear AND p.publication_year <= endYear
OPTIONAL MATCH (p)<-[:PUBLISHED]-(co:Researcher)
WHERE co.normalized_name <> normName
RETURN p.title AS Title, 
       p.publication_year AS Year,
       co.name AS CoAuthors,
       p.doi AS DOI

2. For "With whom did <Name> collaborate most":
WITH '<Name>' AS inputName
WITH toLower(inputName) AS normName
MATCH (r:Researcher {normalized_name: normName})-[:PUBLISHED]->(p:Publication)<-[:PUBLISHED]-(co:Researcher)
RETURN co.name AS CoAuthor, 
       COUNT(p) AS CollaborationCount
ORDER BY CollaborationCount DESC
LIMIT 10

3. Use openalex_url to disambiguate researchers.

4. When the user asks "With whom did <Name> co-author the most", generate:
    WITH '<Name>' AS inputName
    WITH toLower(inputName) AS normName
    MATCH (r:Researcher {normalized_name: normName})
    WITH r.openalex_url AS authorUrl
    MATCH (r:Researcher {openalex_url: authorUrl})-[:PUBLISHED]->(p:Publication)<-[:PUBLISHED]-(co:Researcher)
    RETURN co.name             AS CoAuthor,
           co.openalex_url     AS CoAuthorOpenAlexID,
           COUNT(p)            AS NumCollaborations
    ORDER BY NumCollaborations DESC
    LIMIT 1;

5. When the user asks "How many publications of <Name> are related to <Topic>", generate:
    WITH '<Name>' AS inputName
    WITH toLower(inputName) AS normName, toLower('<Topic>') AS topic
    MATCH (r:Researcher {normalized_name: normName})-[:PUBLISHED]->(p:Publication)

    // look at the researcher’s topical metadata
    OPTIONAL MATCH (r)-[:STUDIES]->(tag:Tag)
    OPTIONAL MATCH (r)-[:WORKS_ON]->(keyword:Keyword)

    WHERE   (p.title        IS NOT NULL AND toLower(p.title)        CONTAINS topic)
        OR  (tag.name       IS NOT NULL AND toLower(tag.name)       CONTAINS topic)
        OR  (keyword.name   IS NOT NULL AND toLower(keyword.name)   CONTAINS topic)

    RETURN COUNT(DISTINCT p) AS NumPublications;

6. When the user asks "In which Journal(Conference) <Name> published the most", generate:
    WITH '<Name>' AS inputName
    WITH toLower(inputName) AS normName
    MATCH (r:Researcher {normalized_name: normName})
    WITH r.openalex_url AS authorUrl
    MATCH (r:Researcher {openalex_url: authorUrl})-[:PUBLISHED]->(p:Publication)-[:PUBLISHED_IN]->(v:Venue)
    WITH v.name            AS VenueName,
         v.type            AS VenueType,
         COUNT(p)          AS NumPublications
    ORDER BY NumPublications DESC
    WITH collect({VenueName:VenueName,VenueType:VenueType,NumPublications:NumPublications}) AS stats
    WITH CASE
           WHEN stats[0].VenueName = 'Venue not found' THEN stats[1]
           ELSE stats[0]
         END AS chosen
    RETURN chosen.VenueName       AS VenueName,
           chosen.VenueType       AS VenueType,
           chosen.NumPublications AS NumPublications;

7. When the user asks "What are the most important topics for <Name>?":
   - Immediately generate the shallow Cypher query (do NOT ask for user input):
        WITH '<Name>' AS inputName
        WITH toLower(inputName) AS normName
        MATCH (r:Researcher {normalized_name: normName})
        OPTIONAL MATCH (r)-[:STUDIES]->(tag:Tag)
        OPTIONAL MATCH (r)-[:WORKS_ON]->(keyword:Keyword)
        RETURN tag.name AS Tag, keyword.name AS Keyword;
   - Do not include any explanatory text - ONLY the Cypher query.
   a) First, ask the user:
      “Would you like a shallow search (using tags and keywords) or a deep search (analyze all publication titles)?”
      — do **not** generate any Cypher yet.

   b) **If** the user answers “shallow”:
      1. Generate **only** this Cypher to fetch tags & keywords:
         WITH '<Name>' AS inputName
         WITH toLower(inputName) AS normName
         MATCH (r:Researcher {normalized_name: normName})
         OPTIONAL MATCH (r)-[:STUDIES]->(tag:Tag)
         OPTIONAL MATCH (r)-[:WORKS_ON]->(keyword:Keyword)
         RETURN tag.name AS Tag, keyword.name AS Keyword;
      2. After the results return:
         - **If** any non-null Tag or Keyword exists, count their frequencies and respond in plain English:
           “Based on these topics, it looks like <TopTopic> is the primary focus.”
         - **If** none exist, tell the user:
           “No tags or keywords were found, so we’ll perform a deep search instead.”  
           Then automatically fall through to step (c).

   c) **If** the user answers “deep” (or after fallback in 7b):
      1. Generate **only** this Cypher to fetch all publication titles:
         WITH '<Name>' AS inputName
         WITH toLower(inputName) AS normName
         MATCH (r:Researcher {normalized_name: normName})
         WITH r.openalex_url AS authorUrl
         MATCH (r:Researcher {openalex_url: authorUrl})-[:PUBLISHED]->(p:Publication)
         RETURN p.title AS Title;
      2. After the titles return, analyze all of the titles (in chat, no code fences, excluding stop words), summarize the primary topic(s)(At most), and respond in plain English:
         “Based on these titles, it seems the primary topic is/are <TopTopic>.”
7.5. When users refer to departments like “ECE,” assume it stands for “Electrical and Computer Engineering.
8. When the user asks:
   "Which research topics show the greatest increase in publications for the <Department> between <Year1> and <Year2>?"
   **Generate only this Cypher, substituting the actual department string and integer years:**

   WITH
     CASE 
       WHEN toLower(trim('<Department>')) IN ['ece', 'electrical and computer engineering'] THEN 'ECE'
       ELSE trim('<Department>')
     END AS deptName,
     toInteger(<Year1>) AS startYear,
     toInteger(<Year2>) AS endYear

   MATCH (d:Department)
     WHERE toLower(d.department) = toLower(deptName)
        OR toLower(coalesce(d.abbr, '')) = toLower(deptName)

   MATCH (d)<-[:BELONGS_TO]-(r:Researcher)
   MATCH (r)-[:PUBLISHED]->(p:Publication)
     WHERE toInteger(p.publication_year) >= startYear
       AND toInteger(p.publication_year) <= endYear
   OPTIONAL MATCH (r)-[:STUDIES]->(t:Tag)
   OPTIONAL MATCH (r)-[:WORKS_ON]->(k:Keyword)
   WITH
     p, startYear, endYear,
     (CASE WHEN t IS NOT NULL THEN ['Tag: ' + t.name] ELSE [] END) +
     (CASE WHEN k IS NOT NULL THEN ['Keyword: ' + k.name] ELSE [] END) AS topics
   WITH
     p, startYear, endYear,
     CASE WHEN size(topics) = 0 THEN ['<no-topic>'] ELSE topics END AS topics
   UNWIND topics AS topic
   WITH
     topic,
     startYear,
     endYear,
     toInteger(p.publication_year) AS year,
     COUNT(DISTINCT p) AS countByYear
   WITH
     topic,
     startYear,
     endYear,
     SUM(CASE WHEN year = startYear THEN countByYear ELSE 0 END) AS startCount,
     SUM(CASE WHEN year = endYear   THEN countByYear ELSE 0 END) AS endCount
   WHERE startCount > 0 OR endCount > 0
   RETURN
     topic,
     startCount,
     endCount,
     endCount - startCount AS increase
   ORDER BY increase DESC
   LIMIT 10;

9. Output format:
   - For steps 4–6 and for each Cypher-generation step above: return **only** the Cypher query.
   - For summarization steps (7b.2 when topics exist, 7c.2 after title analysis): return **only** the plain-English summary, no code.

10. When a user query is given, extract only likely person name tokens and return them strictly as JSON in the form {"tokens": ["..."]}; tokens must be lowercase, preserve order of appearance, keep internal hyphens/apostrophes, exclude numbers, punctuation (other than hyphen/apostrophe), non-name words (institutions, venues, disciplines, verbs, query words, years, quantities, etc.), allow single-token names, and if no names are found return {"tokens": []}.

Key Rules:
1. The 'normalized_name' property exists ONLY on the 'Researcher' node. NEVER use it for filtering on any other node, especially 'Institution' or 'Department'.
2. For date ranges: publication_year >= start AND publication_year <= end
3. For co-authors: collect(co.name) AS CoAuthors
4. Always include publication titles and years
5. Use OPTIONAL MATCH for co-authors in case none exist
6. Include DOI when returning publications
7. If you generate a query with UNION, you MUST ensure all parts of the query return columns with the exact same names. Use aliases (AS) to enforce this.

Output Format:
- ONLY the Cypher query
- No explanations or additional text
- Use the exact patterns above
"""

# Prompt for summarizing publication titles into research topics
TITLE_ANALYSIS_PROMPT = """
Analyze publication titles to extract main research topics.
Return only a 1-2 phrase summary of the primary research focus.
Example: "smart grids and machine learning applications in power systems"
"""

# ─── FastAPI App ──────────────────────────────────────────────────────────────────
app = FastAPI()

# ─── Pydantic Models ─────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    q: str

class SummaryRequest(BaseModel):
    name: str = None
    normalized_name: str = None

class QueryRequest(BaseModel):
    history: List[dict]

# ─── Helpers ─────────────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()

def _last_user_question_text(history):
    """
    Return the last *real* user question (not a control like 'shallow', 'deep',
    or 'select_researcher:<norm>').
    """
    control_prefixes = ("select_researcher:", "shallow", "deep")
    for h in reversed(history):
        if h.get("role") == "user":
            c = (h.get("content") or "").strip()
            cl = c.lower()
            if not (cl in ("shallow", "deep") or cl.startswith("select_researcher:")):
                return c
    return ""

async def _find_name_candidates(driver, free_text: str, limit: int = 200):
    """
    Use tokens from the free text to do CONTAINS lookups against normalized_name/name.
    Returns [{'name': ..., 'normalized_name': ...}, ...]
    """
    import re as _re
    text = _normalize(free_text)
    # tokens like 'petr', 'musilek', 'edward-smith', length >= 3
    tokens = list({t for t in _re.findall(r"[a-z][a-z\-']{2,}", text)})
    if not tokens:
        return []

    q = """
    UNWIND $tokens AS t
    MATCH (r:Researcher)
    WHERE r.normalized_name CONTAINS t
       OR toLower(coalesce(r.name,'')) CONTAINS t
    RETURN r.name AS name, r.normalized_name AS normalized_name, count(*) AS score
    ORDER BY score DESC, name
    LIMIT $limit
    """
    async with driver.session() as session:
        results = await session.run(q, tokens=tokens, limit=limit)
        rows = await results.data()
    # de-dup by normalized_name keeping best score
    seen = {}
    for row in rows:
        key = row["normalized_name"]
        if key not in seen:
            seen[key] = {"name": row["name"], "normalized_name": key}
    return list(seen.values())

def strip_code_fences(text: str) -> str:
    """Remove Markdown code fences so queries execute cleanly in Neo4j."""
    s = text.strip()
    if s.startswith("```") and s.endswith("```"):
        return "\n".join(s.splitlines()[1:-1])
    return text

async def natural_language_to_cypher(history: list[dict]) -> str:
    """Convert conversation history into a Cypher query via OpenAI chat completion."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_1},
        {"role": "system", "content": SYSTEM_PROMPT_2},
    ]
    messages.extend(history)

    # ========= DETAILED DEBUG LOGGING =========
    print("\n" + "=" * 80)
    print("🔍 [LLM DEBUG] Messages sent to OpenAI")
    print("=" * 80)
    for i, msg in enumerate(messages):
        role = msg["role"].upper()
        prefix = "[OTHER_MESSAGE]"
        if msg["content"] == SYSTEM_PROMPT_1:
            prefix = "[SYSTEM_PROMPT_1]"
        elif msg["content"] == SYSTEM_PROMPT_2:
            prefix = "[SYSTEM_PROMPT_2]"
        elif role == "USER":
            prefix = "[USER_MESSAGE]"

        content_preview = msg['content'][:300]
        if len(msg['content']) > 300:
            content_preview += "..."
        print(f"{i+1:02d}. {prefix} ({role}): {content_preview}")
    print("=" * 80)

    # ========= LLM CALL =========
    try:
        resp = await client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=512,
            temperature=0
        )
    except Exception as e:
        print(f"[LLM ERROR] {str(e)}")
        raise

    # ========= LLM RESPONSE DEBUG =========
    raw_response = resp.choices[0].message.content
    print("\n" + "-" * 80)
    print("📩 [LLM RESPONSE - RAW]")
    print("-" * 80)
    print(raw_response)
    print("-" * 80)

    # ========= CLEAN LLM RESPONSE =========
    cleaned = strip_code_fences(raw_response)
    print("\n" + "-" * 80)
    print("✅ [LLM RESPONSE - CLEANED CYTHER QUERY]")
    print("-" * 80)
    print(cleaned)
    print("-" * 80)

    return cleaned

async def execute_cypher(query: str):
    """Run a Cypher query against Neo4j and return a list of result rows."""
    print(f"\n[NEO4J] Executing:\n{query[:500]}{'...' if len(query) > 500 else ''}")

    try:
        async with driver.session() as session:
            result = await session.run(query)
            output = []
            async for record in result:
                row = {}
                for k, v in record.items():
                    # Convert complex types to standard Python types
                    if hasattr(v, "items"):
                        try:
                            row[k] = dict(v.items())
                        except:
                            row[k] = str(v)
                    else:
                        row[k] = v
                output.append(row)

            print(f"[NEO4J] Returned {len(output)} records")
            if output:
                print(f"Sample record: {output[0]}")
            return output
    except Exception as e:
        print(f"[NEO4J ERROR] {str(e)}")
        raise

def extract_dept_and_years(query):
    """Parse department trend queries to extract department name and year range."""
    dept_match = re.search(r"trim\('([^']+)'\)", query)
    year_match = re.search(r"(\d{4})\s+AS\s+startYear[,\s]+(\d{4})", query)

    dept_name = dept_match.group(1) if dept_match else "the department"
    start_year = year_match.group(1) if year_match else "start year"
    end_year = year_match.group(2) if year_match else "end year"
    
    return dept_name, start_year, end_year

def detect_topics_query(text: str) -> str | None:
    """
    Recognise variations of “most important (publishing) topic(s) for <Name>”
    and return the extracted researcher name, or None if no match.
    """
    pattern = re.compile(
        r"""
        most\s+important            # must talk about importance
        (?:\s+publishing)?          # optional “publishing”
        \s+topics?                  # topic / topics / topic(s)
        (?:\s*\(s\))?               # optional “(s)”
        (?:\s+(?:are|is|would\s+be|were|was))?  # optional verb
        \s+for\s+
        (?P<name>.+?)               # capture the researcher’s name
        (?:\?|\.|$)                 # stop at ?, . or EOL
        """,
        re.IGNORECASE | re.VERBOSE,
    )
    m = pattern.search(text)
    return m.group("name").strip() if m else None

def detect_research_areas_query(text: str) -> str | None:
    """Detect queries about a researcher's main research areas based on paper titles."""
    pattern = re.compile(
        r"""
        main\s+research\s+areas?          # main research area/areas
        \s+(?:of|for)\s+
        (?P<name>[^,?.]+?)                # capture the name
        (?:\s*,?\s*based\s+on.*)?         # optional 'based on...' tail
        (?:\?|\.|$)                       # terminate
        """,
        re.IGNORECASE | re.VERBOSE,
    )
    m = pattern.search(text)
    return m.group("name").strip() if m else None

def detect_research_trends_query(text: str):
    """
    Detect:
      - "What are the emerging research trends for Marek Reformat since 2010?"
      - "… between 2010 and 2020"
    Returns (name, start_year, end_year) or None.
    """
    pattern = re.compile(
        r"""
        emerging\s+research\s+trends?\s+(?:for|of)\s+
        (?P<name>[^,?]+?)                    # researcher name
        (?:\s+between\s+(?P<start>\d{4})\s+and\s+(?P<end>\d{4})
         |\s+since\s+(?P<since>\d{4}))       # "between … and …" | "since …"
        (?:\?|\.|$)
        """,
        re.IGNORECASE | re.VERBOSE,
    )
    m = pattern.search(text)
    if not m:
        return None
    name = m.group("name").strip()
    if m.group("since"):
        return name, int(m.group("since")), datetime.now().year
    return name, int(m.group("start")), int(m.group("end"))

def patch_dept_where_clause(q: str) -> str:
    """
    Ensure department trend queries also match the Department.abbr property.
    We only touch queries that already have `MATCH (d:Department)` and a simple
    `WHERE toLower(d.department) = toLower(deptName)` clause.
    """
    pattern = re.compile(
        r"""WHERE\s+toLower\(d\.department\)\s*=\s*toLower\(deptName\)""",
        re.IGNORECASE
    )
    replacement = (
        "WHERE toLower(d.department) = toLower(deptName) "
        "OR toLower(coalesce(d.abbr, '')) = toLower(deptName)"
    )

    new_q, n = pattern.subn(replacement, q)
    if n > 0:
        print("[PATCH] Added abbr fallback to department WHERE clause")
    return new_q


@app.get("/")
async def serve_index():
    """Serve the index.html file."""
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"))

@app.get("/el1.jpg")
async def serve_logo():
    """Serve the logo image."""
    return FileResponse(os.path.join(os.path.dirname(os.path.abspath(__file__)), "el1.jpg"))

@app.post("/search_researchers")
async def search_researchers(req: SearchRequest):
    """
    Return researchers matching the query text.
    """
    q = _normalize(req.q)
    if not q or len(q) < 2:
        return {"matches": []}

    async with driver.session() as session:
        result = await session.run("""
            MATCH (r:Researcher)
            WHERE r.normalized_name CONTAINS $q
               OR toLower(coalesce(r.name, '')) CONTAINS $q
            RETURN r.name AS name, r.normalized_name AS normalized_name
            ORDER BY name
            LIMIT 200;
        """, q=q)
        rows = await result.data()

    return {"matches": rows}

@app.post("/researcher_summary")
async def researcher_summary(req: SummaryRequest):
    """
    Resolve to normalized_name and return a quick profile.
    """
    supplied_name = req.name or req.normalized_name or ""
    norm = _normalize(supplied_name)
    if not norm:
        raise HTTPException(status_code=400, detail="Missing 'name'")

    async with driver.session() as session:
        # Resolve to an exact researcher by normalized_name
        rec_res = await session.run("""
            MATCH (r:Researcher)
            WHERE r.normalized_name = $norm
               OR toLower(coalesce(r.name,'')) = $norm
            RETURN r.name AS name, r.normalized_name AS normalized_name
            LIMIT 1
        """, norm=norm)
        rec = await rec_res.single()

        if not rec:
            # If not an exact match, try a contains match and take the first
            rec_res = await session.run("""
                MATCH (r:Researcher)
                WHERE r.normalized_name CONTAINS $norm
                   OR toLower(coalesce(r.name,'')) CONTAINS $norm
                RETURN r.name AS name, r.normalized_name AS normalized_name
                ORDER BY r.name
                LIMIT 1
            """, norm=norm)
            rec = await rec_res.single()

        if not rec:
            raise HTTPException(status_code=404, detail="Researcher not found")

        full_name = rec["name"]
        resolved_norm = rec["normalized_name"]

        stats_res = await session.run("""
            MATCH (r:Researcher {normalized_name:$n})-[:PUBLISHED]->(p:Publication)
            RETURN COUNT(DISTINCT p) AS publications,
                   [y IN collect(DISTINCT p.publication_year) WHERE y IS NOT NULL] AS years
        """, n=resolved_norm)
        stats = await stats_res.single()

        pubs_total = stats["publications"] if stats else 0
        years = stats["years"] if stats else []
        first_year = min(years) if years else None
        latest_year = max(years) if years else None

        pubs_res = await session.run("""
            MATCH (r:Researcher {normalized_name:$n})-[:PUBLISHED]->(p:Publication)
            RETURN p.title AS Title, p.publication_year AS Year, p.doi AS DOI
            ORDER BY Year DESC, Title
            LIMIT 20
        """, n=resolved_norm)
        pubs_list = await pubs_res.data()

        coauthors_res = await session.run("""
            MATCH (r:Researcher {normalized_name:$n})-[:PUBLISHED]->(p:Publication)<-[:PUBLISHED]-(co:Researcher)
            WHERE co <> r
            RETURN co.name AS CoAuthor, COUNT(DISTINCT p) AS CollaborationCount
            ORDER BY CollaborationCount DESC, CoAuthor
            LIMIT 10
        """, n=resolved_norm)
        coauthors = await coauthors_res.data()

        keywords_res = await session.run("""
            MATCH (r:Researcher {normalized_name:$n})-[:WORKS_ON]->(k:Keyword)
            RETURN k.name AS Keyword
            ORDER BY Keyword
            LIMIT 20
        """, n=resolved_norm)
        keywords = await keywords_res.data()

        tags_res = await session.run("""
            MATCH (r:Researcher {normalized_name:$n})-[:STUDIES]->(t:Tag)
            RETURN t.name AS Tag
            ORDER BY Tag
            LIMIT 20
        """, n=resolved_norm)
        tags = await tags_res.data()

    return {
        "response_type": "researcher_summary",
        "researcher": full_name,
        "stats": {
            "publications": pubs_total,
            "first_year": first_year,
            "latest_year": latest_year
        },
        "coauthors": coauthors,
        "keywords": keywords,
        "tags": tags,
        "publications": pubs_list
    }
@app.post("/query")
async def handle_query(req: QueryRequest):
    """
    Central request handler for all user queries.
    """
    print("\n" + "=" * 80)
    print("INCOMING REQUEST")

    # ─────────────────────────── helpers (local) ────────────────────────────
    import re as _re

    STOP_WORDS = {
        "a", "an", "the", "and", "in", "of", "on", "for", "with", "by", "is", "are", 
        "was", "were", "be", "been", "has", "have", "had", "do", "does", "did", 
        "what", "who", "whom", "which", "where", "when", "why", "how", "show", "me",
        "list", "tell", "give", "find", "about", "concerning", "regarding"
    }

    def _normalize_local(s: str) -> str:
        return _re.sub(r"\s+", " ", (s or "").strip()).lower()

    def _last_real_user_msg(history_list):
        """Return the last non-control user message (not shallow/deep/select_researcher)."""
        for m in reversed(history_list or []):
            if m.get("role") != "user":
                continue
            c = (m.get("content") or "").strip()
            lc = c.lower()
            if lc in ("shallow", "deep"):
                continue
            if lc.startswith("select_researcher:"):
                continue
            return c
        return ""

    def _extract_capitalized_name_tokens(text: str) -> list[str]:
        """
        Pull likely name tokens from the original user wording.
        """
        if not text:
            return []
        toks = _re.findall(r"\b[A-Z][a-zA-Z\-']{2,}\b", text)
        seen, out = set(), []
        for t in toks:
            tl = t.lower()
            if tl not in seen and tl not in STOP_WORDS:
                seen.add(tl)
                out.append(tl)
        return out

    async def _lookup_name_candidates_local(tokens: list[str], limit: int = 200) -> list[dict]:
        """
        Use CONTAINS against normalized_name/name for any of the tokens.
        """
        if not tokens:
            return []
        toks = [t.replace("'", "\\'") for t in tokens]
        where_or = " OR ".join(
            [f"r.normalized_name CONTAINS '{t}' OR toLower(coalesce(r.name,'')) CONTAINS '{t}'" for t in toks]
        )
        cy = f"""
        MATCH (r:Researcher)
        WHERE {where_or}
        RETURN DISTINCT r.name AS name, r.normalized_name AS normalized_name
        ORDER BY name
        LIMIT {limit}
        """
        rows = await execute_cypher(cy) or []
        return [ {"name": r.get("name",""), "normalized_name": r.get("normalized_name","")} for r in rows if r ]

    try:
        history = req.history
        print(f"Payload history length: {len(history)}")

        user_message = history[-1].get("content", "")
        print(f"\nProcessing query: '{user_message}'")

        # ------------------------------------------------------------------
        # Control-word detection
        shallow_requested = any(m.get("content","").lower() == "shallow" for m in history)
        deep_requested    = any(m.get("content","").lower() == "deep"    for m in history)

        selected_norm = None
        for m in reversed(history):
            c = (m.get("content") or "").strip().lower()
            if c.startswith("select_researcher:"):
                selected_norm = _normalize_local(c.split(":", 1)[1])
                break
        
        orig_question = _last_real_user_msg(history)
        name_tokens   = _extract_capitalized_name_tokens(orig_question)

        if selected_norm and name_tokens:
            candidates = await _lookup_name_candidates_local(name_tokens)
            if candidates and all(c.get("normalized_name") != selected_norm for c in candidates):
                selected_norm = None

        if not selected_norm:
            orig_question = _last_real_user_msg(history)
            name_tokens   = _extract_capitalized_name_tokens(orig_question)
            candidates = await _lookup_name_candidates_local(name_tokens) if name_tokens else []

            if not candidates:
                # Fallback to general fuzzy (using tokens but not just capitalized)
                candidates = await _find_name_candidates(driver, orig_question, limit=50)

            if candidates:
                return {
                    "response_type": "researcher_disambiguation",
                    "message": "I found the following people. Who did you mean?",
                    "candidates": candidates
                }

        last_real_msg = _last_real_user_msg(history)

        # 0. Emerging research-trends query
        trend_q = detect_research_trends_query(last_real_msg)
        if trend_q:
            name, start_year, end_year = trend_q
            if selected_norm:
                name = selected_norm
            
            cypher_query = f"""
            WITH '{name}' AS inputName,
                 {start_year} AS startYear,
                 {end_year}   AS endYear
            WITH toLower(inputName) AS normName, startYear, endYear
            MATCH (r:Researcher {{normalized_name: normName}})
                  -[:PUBLISHED]->(p:Publication)
            WHERE p.publication_year >= startYear
              AND p.publication_year <= endYear
            RETURN p.title AS Title, p.publication_year AS Year;
            """
            rows = await execute_cypher(cypher_query)
            titles = [row["Title"] for row in rows if row.get("Title")]

            if not titles:
                return {
                    "response_type": "trend_analysis",
                    "analysis": "No publications found in that period."
                }

            prompt = (
                f"{TITLE_ANALYSIS_PROMPT}\n\n"
                f"(Focus on NEW / rising topics between {start_year} and {end_year})\n"
                + "\n".join(titles[:50])
            )
            chat_resp = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "system", "content": prompt}],
                max_tokens=128,
                temperature=0
            )
            summary = chat_resp.choices[0].message.content.strip()

            return {
                "response_type": "trend_analysis",
                "analysis": summary,
                "results": [{"Title": t} for t in titles]
            }

        # 1. “Main research areas …” query
        areas_name = detect_research_areas_query(last_real_msg)
        if areas_name:
            name = selected_norm or areas_name
            cypher_query = f"""
            WITH '{name}' AS inputName
            WITH toLower(inputName) AS normName
            MATCH (r:Researcher {{normalized_name: normName}})
                  -[:PUBLISHED]->(p:Publication)
            RETURN p.title AS Title;
            """
            rows   = await execute_cypher(cypher_query)
            titles = [row["Title"] for row in rows if row.get("Title")]

            if not titles:
                return {
                    "response_type": "topic_analysis",
                    "analysis": "No publications found."
                }

            prompt  = TITLE_ANALYSIS_PROMPT + "\n\n" + "\n".join(titles[:50])
            chat_resp = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "system", "content": prompt}],
                max_tokens=128,
                temperature=0
            )
            summary = chat_resp.choices[0].message.content.strip()

            return {
                "response_type": "topic_analysis",
                "analysis": summary,
                "results": [{"Title": t} for t in titles]
            }

        # 2. Important-topics question
        name_in_query = detect_topics_query(last_real_msg)
        if name_in_query and not selected_norm:
            return {
                "response_type": "choice_request",
                "message": (
                    "Would you like a shallow search (tags/keywords) "
                    f"or a deep search (all publication titles) for {name_in_query}?"
                )
            }

        collab_intent = bool(re.search(r"\b(co-?author|coauthor|collaborat)\w*\b", last_real_msg, re.I))

        # 3a. Shallow analysis branch
        if shallow_requested or (selected_norm and name_in_query and not deep_requested):
            name = selected_norm or next(
                (detect_topics_query(m["content"])
                 for m in reversed(history) if detect_topics_query(m["content"])),
                None
            ) or "unknown"
            
            cypher_query = f"""
            WITH '{name}' AS inputName
            WITH toLower(inputName) AS normName
            MATCH (r:Researcher {{normalized_name: normName}})
            OPTIONAL MATCH (r)-[:STUDIES]->(tag:Tag)
            OPTIONAL MATCH (r)-[:WORKS_ON]->(keyword:Keyword)
            RETURN tag.name AS Tag, keyword.name AS Keyword;
            """
            rows     = await execute_cypher(cypher_query)
            tags     = [r["Tag"]     for r in rows if r.get("Tag")]
            keywords = [r["Keyword"] for r in rows if r.get("Keyword")]

            if not tags and not keywords:
                return {
                    "response_type": "fallback_deep",
                    "message": "No tags or keywords found—switching to deep search..."
                }

            top_topic = Counter(tags + keywords).most_common(1)[0][0]
            return {
                "response_type": "topic_analysis",
                "analysis": f"Based on tags and keywords, {top_topic} is the primary focus.",
                "results": ([{"Tag": t} for t in tags]
                            + [{"Keyword": k} for k in keywords])
            }

        # 3b. Deep analysis branch
        if deep_requested or (selected_norm and name_in_query and not shallow_requested):
            name = selected_norm or next(
                (detect_topics_query(m["content"])
                 for m in reversed(history) if detect_topics_query(m["content"])),
                None
            ) or "unknown"
            
            cypher_query = f"""
            WITH '{name}' AS inputName
            WITH toLower(inputName) AS normName
            MATCH (r:Researcher {{normalized_name: normName}})
                  -[:PUBLISHED]->(p:Publication)
            RETURN p.title AS Title;
            """
            rows   = await execute_cypher(cypher_query)
            titles = [r["Title"] for r in rows if r.get("Title")]

            if not titles:
                return {
                    "response_type": "topic_analysis",
                    "analysis": "No publications found."
                }

            prompt  = TITLE_ANALYSIS_PROMPT + "\n\n" + "\n".join(titles[:50])
            chat_resp = await client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "system", "content": prompt}],
                max_tokens=128,
                temperature=0
            )
            summary = chat_resp.choices[0].message.content.strip()

            return {
                "response_type": "topic_analysis",
                "analysis": summary,
                "results": [{"Title": t} for t in titles]
            }

        # 4. Generic natural-language → Cypher
        llm_history = history
        if selected_norm:
            llm_history = history + [{
                "role": "system",
                "content": f"User selected exact researcher: normalized_name='{selected_norm}'. "
                           f"When matching (Researcher), use this normalized_name."
            }]

        cypher_query = await natural_language_to_cypher(llm_history)
        cypher_query = patch_dept_where_clause(cypher_query)
        print(f"\nFinal Cypher:\n{cypher_query}")
        results = await execute_cypher(cypher_query)
        print(f"Rows returned: {len(results)}")

        # 5. Department-level trend results
        if "ORDER BY increase DESC" in cypher_query:
            dept_name, start_year, end_year = extract_dept_and_years(cypher_query)
            if not results:
                return {"response_type": "trend_analysis", "analysis": "No trend data found"}

            summary = f"For {dept_name} ({start_year}-{end_year}), top trends:\n"
            summary += "\n".join([
                f"{i+1}. {row['topic']}: {row['startCount']}→{row['endCount']} "
                f"(+{row['increase']})"
                for i, row in enumerate(results[:5])
            ])
            return {
                "response_type": "trend_analysis",
                "analysis": summary,
                "results": results
            }

        # 6. Co-author publication queries
        if "collect(co.name)" in cypher_query.lower():
            formatted = [{
                "title":     row.get("Title", "Untitled"),
                "year":      row.get("Year",  "Unknown"),
                "venue":     row.get("Venue", "Unknown"),
                "coauthors": ", ".join(row.get("CoAuthors", [])) or "None"
            } for row in results]

            return {
                "response_type": "publications_with_coauthors",
                "cypher_query": cypher_query,
                "formatted_results": formatted,
                "raw_results": results
            }

        # 7. Default
        return {
            "cypher_query": cypher_query,
            "results": results
        }

    except Exception as e:
        print(f"\nERROR: {str(e)}")
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
