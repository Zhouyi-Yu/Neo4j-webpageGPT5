# Neo4j Research Q&A System

[**Changelog**](CHANGELOG.md)

A high-performance, LLM-driven research discovery engine for the University of Alberta, powered by **FastAPI**, **Neo4j**, and **OpenAI**.

## 🚀 System Architecture

This system is built with **FastAPI** to provide a high-concurrency, asynchronous backend capable of orchestrating complex LLM and Graph Database operations in real-time.

### Key Features
- **Asynchronous Pipeline**: Full non-blocking I/O for OpenAI and Neo4j.
- **Strict Logic Parity**: Precise replication of the original scientific discovery logic.
- **Speculative Synthesis**: Parallel intent classification and semantic discovery.
- **Robust Validation**: Pydantic-powered request and response schemas.

## 📁 Project Structure

- `main.py`: The FastAPI application entry point.
- `backend.py`: Core asynchronous pipeline logic.
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
./start.sh
```
- **Access the App**: Open [http://localhost:5173](http://localhost:5173) in your browser.
- **View Control Flow**: Open [http://localhost:5173/cfg.html](http://localhost:5173/cfg.html) and see [CFG_README.md](CFG_README.md) for details.

## 🔍 Troubleshooting

### Neo4j Authentication
If search results are empty and the logs show `Neo.ClientError.Security.Unauthorized`, double-check your `.env` credentials. Verify you can log into `http://localhost:7474` with the same username and password.

### API Key Issues
Ensure your `OPENAI_API_KEY` is active and has sufficient credits. The system uses `gpt-4o-mini` for cost-effective, real-time responses.

## 📊 System Analysis
For a detailed analysis of the system's control flow, see [CFG_README.md](CFG_README.md).
