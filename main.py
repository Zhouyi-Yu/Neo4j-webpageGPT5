import os
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Request, HTTPException, Depends, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

# Import the async backend pipeline
from backend import answer_question

app = FastAPI(title="Neo4j Researcher Search API")

# Session management middleware
# In production, use a secure secret key from an environment variable
SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "dev-secret-key-change-in-production")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Base directory for serving static files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEBUG_LOG_FILE = os.path.join(BASE_DIR, "debug_log.txt")

# Pydantic models for validation
class QueryRequest(BaseModel):
    question: str
    selected_user_id: Optional[str] = None

class DebugLogEntry(BaseModel):
    timestamp: str
    question: str
    answer: str
    intent: Dict[str, Any]
    cypher: str
    dbRows: List[Dict[str, Any]]
    semanticHits: List[Dict[str, Any]]
    telemetry: Optional[Dict[str, Any]] = None

# ROUTES

@app.get("/")
async def root():
    """Serve the main UI (index.html)."""
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.get("/index.html")
async def index_html():
    """Alternative route for index.html."""
    return FileResponse(os.path.join(BASE_DIR, "index.html"))

@app.post("/api/query")
async def api_query(request: Request, query: QueryRequest):
    """
    Main API endpoint.
    FastAPI automatically validates the request body against QueryRequest model.
    """
    question = query.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Missing 'question' in request body.")

    # Get conversation history from session
    # FastAPI's SessionMiddleware puts the session object in request.session
    conversation_history = request.session.get("conversation_history", [])
    
    try:
        # Call the async backend
        result = await answer_question(question, conversation_history, query.selected_user_id)
        
        # If there's an error key in the result, we still want to update history if possible
        answer = result.get("answer", "")
        
        # Update conversation history
        conversation_history.append({"role": "user", "content": question})
        conversation_history.append({"role": "assistant", "content": answer})
        
        # Keep only last 10 messages (5 Q&A pairs)
        conversation_history = conversation_history[-10:]
        request.session["conversation_history"] = conversation_history
        
        # If an error occurred inside the pipeline but was caught, return as 200 
        # (Frontend will check the result object for debug data)
        return result
    except Exception as e:
        print(f"CRITICAL: Uncaught error in api_query: {e}")
        import traceback
        traceback.print_exc()
        # In case of total crash, still try to return a structural error
        return JSONResponse(
            status_code=500,
            content={
                "answer": f"A system error occurred: {str(e)}",
                "intent": {},
                "cypher": "",
                "dbRows": [],
                "semanticHits": [],
                "error": str(e)
            }
        )

@app.post("/api/log-debug")
async def log_debug(entry: DebugLogEntry):
    """Append a debug entry to the debug_log.txt file."""
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n")
        return {"status": "success"}
    except Exception as e:
        print(f"Error writing debug log: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to write debug log: {str(e)}")

@app.get("/api/debug-log")
async def get_debug_log():
    """Retrieve the contents of the debug_log.txt file."""
    try:
        if not os.path.exists(DEBUG_LOG_FILE):
            return Response(content="", media_type="text/plain")
        
        # Use a generator or limited read if file is huge, but for now 1MB is fine
        with open(DEBUG_LOG_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        
        return Response(content=content, media_type="text/plain")
    except Exception as e:
        print(f"Error reading debug log: {e}")
        return Response(content=f"Error reading log file: {e}", status_code=500, media_type="text/plain")

# Mount static files to serve logos, prompts, etc.
# Check if directories exist before mounting
for folder in ["logos", "prompts", "temp"]:
    if os.path.isdir(os.path.join(BASE_DIR, folder)):
        app.mount(f"/{folder}", StaticFiles(directory=os.path.join(BASE_DIR, folder)), name=folder)

# Static file serving for any other files in the root
# Note: Root static files should be served via explicit routes if possible, 
# or mount the entire root directory (carefully) at the end.
@app.get("/{filename}")
async def serve_file(filename: str):
    file_path = os.path.join(BASE_DIR, filename)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)
