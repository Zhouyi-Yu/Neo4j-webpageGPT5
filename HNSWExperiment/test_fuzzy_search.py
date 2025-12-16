
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
        
        # Ensure the index is online (might take a moment if just created, but usually fast)
        # In a real scenario, we'd wait for the index, but for this simple test we assume it's there 
        # or we might fail if the user hasn't run superDBmaker.py yet.

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
    # If this fails, it's likely because the Fulltext Index hasn't been created yet.
    try:
        updated_intent, candidates = resolve_author(intent_obj)
    except Exception as e:
        pytest.fail(f"resolve_author failed. Did you run superDBmaker.py to create the index? Error: {e}")

    # We expect candidates because "TestMark Refamt" is not an exact match, 
    # so the fuzzy logic should kick in and return a list of candidates.
    
    # Check if we got the correct candidate
    found = False
    if candidates:
        for cand in candidates:
            if cand['userId'] == TEST_USER_ID:
                found = True
                break
    
    assert found, f"Fuzzy search failed to find UAlberta researcher '{TEST_RESEARCHER_NAME}' with query '{intent_obj['author']}'"

def test_external_researcher_ignored(driver, setup_test_data):
    """
    Test that non-UAlberta researchers are NOT returned even if names match.
    """
    # Query exactly for the external researcher
    intent_obj = {"author": "TestExternal Researcher"}
    
    updated_intent, candidates = resolve_author(intent_obj)
    
    # Should be None or empty candidates because we filter WHERE userId IS NOT NULL OR ccid IS NOT NULL
    # The exact match logic in resolve_author might have been replaced by fuzzy-only or combined.
    # Based on my change, it's purely fuzzy/index-based with the filter.
    
    found_external = False
    if candidates:
        for cand in candidates:
            if cand.get('name') == 'TestExternal Researcher':
                found_external = True
    
    assert not found_external, "Search should NOT return researchers without userId/ccid (Non-UAlberta)"

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
