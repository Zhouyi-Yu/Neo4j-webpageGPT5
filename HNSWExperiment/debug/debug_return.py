import os
import json
from dotenv import load_dotenv

load_dotenv()

from backend import answer_question

def debug():
    q = "Give 3 papers by alan wilman"
    print(f"Query: {q}")
    result = answer_question(q)
    print("DEBUG INTENT:", json.dumps(result.get("intent"), indent=2))
    print("DEBUG CYPHER:", result.get("cypher"))
    # print("RAW RESULT JSON:")
    # print(json.dumps(result, indent=2, default=str))

if __name__ == "__main__":
    debug()
