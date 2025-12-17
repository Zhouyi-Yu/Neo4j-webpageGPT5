import os
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def run_debug():
    with driver.session() as session:
        print("--- DEBUGGING ALAN WILMAN ---")
        # 1. Check Person node
        print("\n1. Searching for Person 'Alan Wilman' (fuzzy or exact)...")
        res = session.run("""
            MATCH (p:Person)
            WHERE toLower(p.name) CONTAINS 'alan' AND toLower(p.name) CONTAINS 'wilman'
               OR toLower(p.normalized_name) CONTAINS 'wilman'
            RETURN p.name AS name, p.userId AS userId, p.normalized_name AS normalized_name
        """).data()
        print("Person Matches:", res)

        if res:
            uid = res[0]['userId']
            print(f"\n2. Checking connections for userId='{uid}'...")
            
            # 2. Check HAS_PROFILE
            res_prof = session.run("""
                MATCH (p:Person {userId: $uid})
                OPTIONAL MATCH (p)-[r:HAS_PROFILE]->(ap:AuthorProfile)
                RETURN r, ap.name, ap.normalized_name, ap.openalex_url
            """, uid=uid).data()
            print("HAS_PROFILE:", res_prof)
            
            # 3. Check Publications from Profile
            if res_prof and res_prof[0]['ap.name']:
                print("\n3. Checking Publications from AuthorProfile...")
                res_pubs = session.run("""
                    MATCH (p:Person {userId: $uid})-[:HAS_PROFILE]->(ap:AuthorProfile)
                    MATCH (ap)-[:PUBLISHED]->(pub:Publication)
                    RETURN count(pub) as pub_count, collect(pub.title)[0..3] as sample_titles
                """, uid=uid).data()
                print("Publications via Profile:", res_pubs)
            else:
                print("\n3. SKIP: No AuthorProfile found.")
                
            # 4. Check Legacy Researcher Node (if any)
            print("\n4. Checking Legacy Researcher node...")
            res_res = session.run("""
                MATCH (r:Researcher)
                WHERE r.normalized_name = $norm
                OPTIONAL MATCH (r)-[:PUBLISHED]->(pub:Publication)
                RETURN r.name, count(pub) as pub_count
            """, norm=res[0]['normalized_name']).data()
            print("Researcher Node:", res_res)

        print("\n--- COMPARISON: WITOLD PEDRYCZ ---")
        res_witold = session.run("""
            MATCH (p:Person) 
            WHERE toLower(p.name) CONTAINS 'witold' AND toLower(p.name) CONTAINS 'pedrycz'
            RETURN p.name, p.userId
        """).data()
        print("Witold Person:", res_witold)
        if res_witold:
             uid_w = res_witold[0]['userId']
             res_w_pubs = session.run("""
                MATCH (p:Person {userId: $uid})-[:HAS_PROFILE]->(ap:AuthorProfile)-[:PUBLISHED]->(pub:Publication)
                RETURN count(pub) as count
             """, uid=uid_w).data()
             print("Witold Pubs via Profile:", res_w_pubs)

if __name__ == "__main__":
    try:
        run_debug()
    finally:
        driver.close()
