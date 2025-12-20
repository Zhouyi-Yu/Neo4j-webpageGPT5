import os
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

uri = os.getenv("NEO4J_URI", "bolt://localhost:7687").strip()
user = os.getenv("NEO4J_USER", "neo4j").strip()
password = os.getenv("NEO4J_PASSWORD", "password").strip()

print(f"Attempting to connect to {uri} as {user}...")
print(f"Password starts with: {password[:2]}... (length: {len(password)})")

try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        result = session.run("RETURN 1 AS one")
        record = result.single()
        if record and record["one"] == 1:
            print("SUCCESS: Connected to Neo4j!")
        else:
            print("FAILED: Connected but query failed.")
except Exception as e:
    print(f"ERROR: {e}")
finally:
    if 'driver' in locals():
        driver.close()
