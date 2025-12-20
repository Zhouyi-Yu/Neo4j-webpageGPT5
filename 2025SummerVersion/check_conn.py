
from neo4j import GraphDatabase
import sys

uri = "bolt://129.128.218.235:7687"
user = "neo4j"
password = "password"

try:
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print("Connected successfully to " + uri)
    driver.close()
except Exception as e:
    print(f"Failed to connect: {e}")
    sys.exit(1)
