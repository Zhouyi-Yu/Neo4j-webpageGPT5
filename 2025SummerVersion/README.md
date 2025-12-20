# Neo4j-webpageGPT5

Flask service that turns natural-language research questions into Cypher with OpenAI, runs them against a Neo4j graph built from institutional CSVs + OpenAlex exports, and serves a minimal web UI (`index.html`).

## What’s here
- LLM-assisted Cypher generation and execution (`app.py`).
- Researcher lookup (`/search_researchers`) and quick profile summaries (`/researcher_summary`).
- Graph rebuild helper that ingests CSVs into Neo4j (`superDBmaker.py`).
- Local data workspace (`infocsv/`) ignored from git to keep large CSVs out of the repo.

## Quick start
1) Python 3.10+ and a reachable Neo4j instance.
2) Create a venv and install deps:
```
python -m venv .venv
source .venv/bin/activate
pip install flask neo4j openai
```
3) Configure secrets:
- Set `OPENAI_API_KEY`.
- Update `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` in `app.py` (defaults point to a demo instance).
4) Run the API/UI:
```
python app.py
# visit http://localhost:5000/
```

## API highlights
- `POST /search_researchers` with `{"q": "musilek"}` → up to 25 matches.
- `POST /researcher_summary` with `{"name": "Petr Musilek"}` → pubs, co-authors, tags/keywords.
- `POST /query` drives the LLM workflow; send a chat-style `history`, e.g.:
```
curl -X POST http://localhost:5000/query \
  -H "Content-Type: application/json" \
  -d '{"history":[{"role":"user","content":"What did Petr Musilek publish in 2020?"}]}'
```
Responses include the Cypher used plus formatted results depending on the branch taken.

## Data + ingestion
- `infocsv/` holds local CSV exports (ignored by git). Keep large files out of commits.
- To rebuild the Neo4j graph, place the expected CSVs in Neo4j’s `import` folder (see docstring in `superDBmaker.py`) and run:
```
python superDBmaker.py --wipe
```
- Logs from the Flask app are written to `log.txt`.

## Notes
- GitHub rejects pushes with files >100 MB; rely on the `.gitignore` in `infocsv/` to avoid committing large datasets.
- `openalex_to_csv.py` and related helpers assist in exporting OpenAlex data if you need fresh CSVs.
