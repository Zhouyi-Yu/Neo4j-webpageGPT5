# Neo4j Research Q&A System

A powerful, LLM-driven question-answering system for University of Alberta research publications, powered by Neo4j graph database and OpenAI.

## 🚀 Recent Update: FastAPI Migration

The project has recently been migrated from Flask to **FastAPI** to enable:
- **Asynchronous I/O**: High-performance handling of concurrent LLM and Neo4j requests.
- **Improved Performance**: Reduced latency for I/O-bound operations.
- **Strict Logic Parity**: The backend logic (`backend.py`) remains **100% functionally identical** to the original implementation (found in `olderVer/`). Every branching decision, LLM prompt, and processing step has been preserved.

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python 3.10+)
- **Database**: Neo4j (Graph Database with Vector Index)
- **AI**: OpenAI (gpt-4o-mini for chat, text-embedding-3-large for vectors)
- **Validation**: Pydantic
- **Frontend**: HTML5/JavaScript (Vanilla)

## 📁 Project Structure

- `main.py`: The FastAPI application entry point.
- `backend.py`: Core asynchronous pipeline logic (parity version).
- `olderVer/`: Contains the original Flask-based `app.py` and `backend.py` for reference.
- `index.html`: The main chat interface.
- `prompts/`: System prompts for intent classification, Cypher generation, and synthesis.
- `.env`: Environment variables (API keys and database credentials).

## 🚦 Getting Started

### 1. Prerequisites
Ensure you have Python 3.10+ and a running Neo4j instance.

### 2. Installation
```bash
pip install -r requirements.txt
```

### 3. Configuration
Create/Update your `.env` file:
```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
OPENAI_API_KEY=your_openai_api_key
```

### 4. Running the Application
```bash
uvicorn main:app --host 0.0.0.0 --port 5001 --reload
```
Open `http://localhost:5001` in your browser.

## 🔍 Troubleshooting

### Neo4j Authentication
If search results are empty and the logs show `Neo.ClientError.Security.Unauthorized`, double-check your `.env` credentials. Verify you can log into `http://localhost:7474` with the same username and password.

### API Key Issues
Ensure your `OPENAI_API_KEY` is active and has sufficient credits. The system uses `gpt-4o-mini` for cost-effective, real-time responses.

## 📊 System Analysis
For a detailed analysis of the system's control flow, see [CFG_README.md](CFG_README.md).
