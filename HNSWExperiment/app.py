"""
app.py — Flask wrapper around the new tryGPT5_v2 pipeline.

Endpoints:
  GET  /           -> serves index.html UI
  POST /api/query  -> accepts {"question": "..."} and returns JSON:
                      {
                        "answer": "...",
                        "intent": {...},
                        "cypher": "...",
                        "dbRows": [...],
                        "semanticHits": [...]
                      }
"""

import os
import json
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.exceptions import HTTPException

# Import your multi-stage pipeline (same folder as this app.py)
from backend import answer_question

# Create Flask app
app = Flask(__name__)

# Base directory for serving index.html
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Debug log file path
DEBUG_LOG_FILE = os.path.join(BASE_DIR, "debug_log.txt")


# ───────────────────────────────────────────────────────────────
# ROUTES
# ───────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def root():
    """
    Serve the main UI (index.html) from the same folder as app.py.
    """
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/api/query", methods=["POST"])
def api_query():
    """
    Main API endpoint used by the new frontend.
    Expects JSON: { "question": "..." }
    """
    data = request.get_json(silent=True) or {}

    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Missing 'question' in request body."}), 400

    try:
        result = answer_question(question)
        # result is already a dict with:
        #   answer, intent, cypher, dbRows, semanticHits
        return jsonify(result), 200
    except Exception as e:
        # Log the error to Flask's logger
        app.logger.exception("Error while answering question")
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500


# Optional: direct route to /index.html (handy when testing)
@app.route("/index.html", methods=["GET"])
def index_html():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(BASE_DIR, filename)


@app.route("/api/log-debug", methods=["POST"])
def log_debug():
    """
    Append a debug entry to the debug_log.txt file.
    Expects JSON with: timestamp, question, answer, intent, cypher, dbRows, semanticHits
    """
    data = request.get_json(silent=True) or {}
    
    try:
        # Append the entry as a single JSON line
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False) + "\n")
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        app.logger.exception("Error writing to debug log")
        return jsonify({"error": "Failed to write debug log", "detail": str(e)}), 500


@app.route("/api/debug-log", methods=["GET"])
def get_debug_log():
    """
    Retrieve the contents of the debug_log.txt file.
    Returns the raw text content (newline-delimited JSON).
    """
    try:
        if not os.path.exists(DEBUG_LOG_FILE):
            return "", 200
        
        with open(DEBUG_LOG_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        
        return content, 200, {"Content-Type": "text/plain; charset=utf-8"}
    except Exception as e:
        app.logger.exception("Error reading debug log")
        return jsonify({"error": "Failed to read debug log", "detail": str(e)}), 500


# ───────────────────────────────────────────────────────────────
# GLOBAL ERROR HANDLERS (OPTIONAL)
# ───────────────────────────────────────────────────────────────

@app.errorhandler(HTTPException)
def handle_http_exception(exc: HTTPException):
    """
    Return JSON for any Werkzeug/Flask HTTP exceptions.
    """
    response = {
        "error": exc.name,
        "code": exc.code,
        "description": exc.description,
    }
    return jsonify(response), exc.code


@app.errorhandler(Exception)
def handle_unexpected_exception(exc: Exception):
    """
    Catch-all for other uncaught exceptions.
    """
    app.logger.exception("Unhandled exception")
    return jsonify({"error": "Internal server error", "detail": str(exc)}), 500


# ───────────────────────────────────────────────────────────────
# ENTRY POINT
# ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # debug=True is handy locally; turn off in production.
    app.run(host="0.0.0.0", port=5001, debug=True)
