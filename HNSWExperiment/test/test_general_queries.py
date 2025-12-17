import os
import json
from dotenv import load_dotenv

# Load env before importing backend to ensure keys are present
load_dotenv()

from backend import answer_question

# Test Cases
TEST_CASES = [
    {
        "name": "Regression: Alan Wilman (Exact)",
        "question": "Give 3 papers by alan wilman",
        "expected_intent_upgrade": "AUTHOR_PUBLICATIONS_RANGE",
        "expected_author": "Alan Wilman"
    },
    {
        "name": "Control: Witold Pedrycz (Exact)",
        "question": "Show me work by Witold Pedrycz",
        "expected_intent_type": "AUTHOR_PUBLICATIONS_RANGE" 
    },
    {
        "name": "Fuzzy: Marek Refamt (Typo)",
        "question": "papers by Marek Refamt",
        "expected_author": "Marek Reformat"
    },
    {
        "name": "Topic Search (No Author)",
        "question": "recent papers on reinforcement learning",
        # Should NOT trigger author resolution
        "expected_author": None
    },
    {
        "name": "Ambiguous/Candidate List",
        "question": "Who is 'Li'?", 
        # "Li" is very short, might match many. We expect a candidate list or simple answer.
        # Just checking it doesn't crash.
        "check_candidates": True
    }
]

def run_tests():
    print("=== RUNNING GENERAL QUERY TESTS ===\n")
    
    for case in TEST_CASES:
        q = case["question"]
        print(f"--- Test: {case['name']} ---")
        print(f"Query: '{q}'")
        
        try:
            result = answer_question(q)
            
            intent_obj = result.get("intent", {})
            final_intent = intent_obj.get("intent")
            resolved_author = intent_obj.get("author")
            db_rows = result.get("dbRows", [])
            candidates = result.get("candidates")
            
            print(f"Final Intent: {final_intent}")
            print(f"Resolved Author: {resolved_author}")
            print(f"DB Rows Returned: {len(db_rows)}")
            if candidates:
                print(f"Candidates Found: {[c['name'] for c in candidates]}")
            
            # Checks
            if "expected_intent_upgrade" in case:
                if final_intent != case["expected_intent_upgrade"]:
                    print(f"FAILURE: Expected intent {case['expected_intent_upgrade']}, got {final_intent}")
                else:
                    print("SUCCESS: Intent upgraded correctly.")
            
            if case.get("expected_author"):
                if resolved_author != case["expected_author"]:
                    print(f"FAILURE: Expected author {case['expected_author']}, got {resolved_author}")
                else:
                    print(f"SUCCESS: Author resolved to {resolved_author}")
            
            if case.get("check_candidates"):
                if candidates:
                    print("SUCCESS: Candidates returned.")
                else:
                    print("INFO: No candidates returned (might be 0 or 1 match).")
            
            print("--------------------------------------------------\n")
            
        except Exception as e:
            print(f"ERROR: {e}\n")

if __name__ == "__main__":
    run_tests()
