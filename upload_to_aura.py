# upload_to_aura.py
from neo4j import GraphDatabase
import os

URI = "neo4j+s://xxxxx.databases.neo4j.io"  # From Step 1
AUTH = ("neo4j", "your-password-here")

driver = GraphDatabase.driver(URI, auth=AUTH)

# Example: Bulk load from CSV
def load_data():
    with driver.session() as session:
        # Your LOAD CSV or CREATE queries here
        session.run("""
            LOAD CSV WITH HEADERS FROM 'file:///publications.csv' AS row
            CREATE (:Publication {
                title: row.title,
                year: toInteger(row.year)
            })
        """)

load_data()
driver.close()