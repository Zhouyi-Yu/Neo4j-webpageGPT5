
import os
import sys
import pytest
from neo4j import GraphDatabase

# Add the current directory to sys.path to make sure we can import tryGPT5_v2
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tryGPT5_v2 import resolve_author, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Test Configuration
TEST_RESEARCHER_NAME = "TestMarek Reformat"
TEST_RESEARCHER_NORM = "testmarek reformat"
TEST_USER_ID = "test_user_123"

@pytest.fixture(scope="module")
def driver():
    uri = os.getenv("NEO4J_URI", NEO4J_URI)
    user = os.getenv("NEO4J_USER", NEO4J_USER)
    password = os.getenv("NEO4J_PASSWORD", NEO4J_PASSWORD)
    
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
    except Exception as e:
        pytest.skip(f"Could not connect to Neo4j at {uri}: {e}")
        
    yield driver
    driver.close()

@pytest.fixture(scope="function")
def setup_test_data(driver):
    """
    Creates a dummy UAlberta researcher and a dummy non-UAlberta researcher.
    """
    with driver.session() as session:
        # 1. Create a UAlberta researcher (has userId)
        session.run("""
            MERGE (r:Researcher {userId: $userId})
            SET r.name = $name,
                r.normalized_name = $norm_name,
                r.ccid = 'testccid'
        """, userId=TEST_USER_ID, name=TEST_RESEARCHER_NAME, norm_name=TEST_RESEARCHER_NORM)

        # 2. Create a Non-UAlberta researcher (no userId/ccid)
        session.run("""
            MERGE (r:Researcher {openalex_url: 'https://openalex.org/test_external'})
            SET r.name = 'TestExternal Researcher',
                r.normalized_name = 'testexternal researcher'
            REMOVE r.userId, r.ccid
        """)
        
        # Ensure the index is online
        # Create the index if it doesn't exist to make the test self-contained
        session.run("""
            CREATE FULLTEXT INDEX researcher_name_index IF NOT EXISTS
            FOR (r:Researcher) ON EACH [r.name, r.normalized_name]
        """)
        
        # Wait a brief moment or call db.awaitIndex/equivalents if possible. 
        # For simplicity in this test script, we force a wait or check status.
        import time
        for _ in range(10):
            result = session.run("SHOW INDEXES YIELD name, state WHERE name = 'researcher_name_index'").single()
            if result and result["state"] == "ONLINE":
                break
            time.sleep(0.5)

    yield

    # Teardown
    with driver.session() as session:
        session.run("MATCH (r:Researcher {userId: $userId}) DETACH DELETE r", userId=TEST_USER_ID)
        session.run("MATCH (r:Researcher {openalex_url: 'https://openalex.org/test_external'}) DETACH DELETE r")

def test_fuzzy_search_ualberta_only(driver, setup_test_data):
    """
    Test that:
    1. Fuzzy search works (typo handling).
    2. Only UAlberta researchers are returned.
    """
    # Case 1: Fuzzy match for the UAlberta researcher (Typo: "TestMark Refamt")
    # "TestMarek Reformat" should match "TestMark Refamt" with fuzzy search
    intent_obj = {"author": "TestMark Refamt"} 
    
    # We need to ensure the index exists for this to work.
    try:
        updated_intent, candidates = resolve_author(intent_obj)
    except Exception as e:
        pytest.fail(f"resolve_author failed. Did you run superDBmaker.py to create the index? Error: {e}")

    # We expect candidates because "TestMark Refamt" is not an exact match, 
    # so the fuzzy logic should kick in and return a list of candidates.
    assert candidates is not None, "Expected fuzzy candidates for misspelled name, got None"
    assert len(candidates) > 0, "Expected at least one candidate"
    
    # Check if we got the correct candidate
    found = False
    for cand in candidates:
        if cand['userId'] == TEST_USER_ID:
            found = True
            break
    
    assert found, f"Fuzzy search failed to find UAlberta researcher '{TEST_RESEARCHER_NAME}' with query '{intent_obj['author']}'"

def test_exact_match_priority(driver, setup_test_data):
    """
    Test that an exact match returns immediately without a candidate list.
    """
    intent_obj = {"author": TEST_RESEARCHER_NAME}
    updated_intent, candidates = resolve_author(intent_obj)
    
    # Expect candidates to be None because we found an exact match
    assert candidates is None, "Exact match should NOT return a candidate list"
    assert updated_intent.get("authorUserId") == TEST_USER_ID, "Exact match should set authorUserId"

def test_external_researcher_ignored(driver, setup_test_data):
    """
    Test that non-UAlberta researchers are NOT returned even if names match.
    """
    # Query exactly for the external researcher
    intent_obj = {"author": "TestExternal Researcher"}
    
    updated_intent, candidates = resolve_author(intent_obj)
    
    # Should be None or empty candidates because we filter WHERE userId IS NOT NULL OR ccid IS NOT NULL
    
    found_external = False
    if candidates:
        for cand in candidates:
            if cand.get('name') == 'TestExternal Researcher':
                found_external = True
    
    assert not found_external, "Search should NOT return researchers without userId/ccid (Non-UAlberta)"
    # Also ensure we didn't accidentally resolve it as an exact match
    assert updated_intent.get("authorUserId") is None, "Should not resolve external researcher ID"

if __name__ == "__main__":
    # Manual run if executed as script
    try:
        # Quick check for index
        d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        with d.session() as s:
            r = s.run("SHOW INDEXES YIELD name WHERE name = 'researcher_name_index'").data()
            if not r:
                print("⚠️  WARNING: 'researcher_name_index' not found. Please run 'python3 superDBmaker.py' first!")
        d.close()
    except Exception:
        pass

    sys.exit(pytest.main(["-v", __file__]))
