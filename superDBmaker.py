#!/usr/bin/env python3
"""
superDBmaker.py  (Community-safe full version)
----------------------------------------------
Rebuild your Neo4j knowledge graph by combining BOTH:
  1) Institutional data from legacy CSVs (sys_users, departments, annual reports, keywords, tags, subclusters)
  2) OpenAlex-harvested CSVs (researchers_openalex, publications, venues, institutions, authorship links)

This version avoids the Enterprise-only NODE KEY constraint by using a synthetic
unique property `Venue.key = lower(name) + '|' + lower(type)`.

Expected CSVs in Neo4j's IMPORT folder:

# Institutional / legacy
- sys_users.csv
- academic_annual_reports.csv
- research_keywords.csv
- research_tags.csv
- 11-all-subclusters.csv

# OpenAlex export
- researchers_openalex.csv
- publications.csv
- venues.csv
- publication_venue.csv
- authorship.csv
- coauthor_relationships.csv
- institutions.csv
- author_institution.csv

Usage:
  python3 superDBmaker.py --wipe
  # add --database <name> if using Neo4j Enterprise multi-db

Config (defaults follow your previous file; can be overridden via env vars):
  URI:  bolt://129.128.218.235:7687  (ENV NEO4J_URI)
  USER: neo4j                        (ENV NEO4J_USER)
  PASS: password                     (ENV NEO4J_PASSWORD)
  DB:   (server default)             (ENV NEO4J_DATABASE)
"""

from __future__ import annotations
import argparse
import os
import sys
from typing import Iterable, Optional
from neo4j import GraphDatabase


# ── Configuration (follows your previous databaseMaking.py style, with env overrides) ──
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://129.128.218.235:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
DEFAULT_DATABASE: Optional[str] = os.getenv("NEO4J_DATABASE")  # None => server default


# ── Helpers ───────────────────────────────────────────────────────────────────
def _q(name: str) -> str:
    """Backtick-quote an identifier safely for DROP statements."""
    return f"`{name.replace('`', '``')}`"


def run(session, query: str, **params):
    """Run a Cypher query."""
    return session.run(query, **params)


def wipe_database(driver, database: Optional[str] = DEFAULT_DATABASE):
    """Drop constraints/indexes (except LOOKUP) and delete all data."""
    print("⏳ Wiping database (constraints, indexes, data)...")
    with driver.session(database=database) if database else driver.session() as session:
        # Drop constraints
        try:
            res = run(session, "SHOW CONSTRAINTS")
            names = [r.get("name") or r.get("constraintName") for r in res if (r.get("name") or r.get("constraintName"))]
            for name in names:
                try:
                    run(session, f"DROP CONSTRAINT {_q(name)} IF EXISTS")
                except Exception as e:
                    print(f"  ⚠️ Could not drop constraint {name}: {e}")
        except Exception as e:
            print(f"  ⚠️ Could not enumerate constraints: {e}")

        # Drop indexes (skip LOOKUP)
        try:
            res = run(session, "SHOW INDEXES")
            for r in res:
                name = r.get("name")
                itype = r.get("type")
                if not name or str(itype).upper() == "LOOKUP":
                    continue
                try:
                    run(session, f"DROP INDEX {_q(name)} IF EXISTS")
                except Exception as e:
                    print(f"  ⚠️ Could not drop index {name}: {e}")
        except Exception as e:
            print(f"  ⚠️ Could not enumerate indexes: {e}")

        # Delete all data
        run(session, "MATCH (n) DETACH DELETE n")
    print("✅ Database wiped.")


def exec_statements(driver, statements: Iterable[str], database: Optional[str] = DEFAULT_DATABASE, label: str = ""):
    """Execute a list of Cypher statements, reporting progress."""
    stmts = list(statements)
    with driver.session(database=database) if database else driver.session() as session:
        for i, stmt in enumerate(stmts, 1):
            try:
                run(session, stmt)
                if label:
                    print(f"  ✅ [{label}] {i}/{len(stmts)}")
            except Exception as e:
                print(f"  ❌ Error running statement {i}/{len(stmts)}:\n{stmt}\n↳ {e}")
                raise


# ── Cypher blocks ─────────────────────────────────────────────────────────────
def constraints_and_indexes() -> list[str]:
    """All constraints & indexes from old + new flows (idempotent)."""
    return [
        # Researcher: unique by OpenAlex author URL (new flow)
        """
        CREATE CONSTRAINT researcher_openalex_unique IF NOT EXISTS
        FOR (r:Researcher) REQUIRE r.openalex_url IS UNIQUE;
        """,

        # Publication: unique by OpenAlex work URL
        """
        CREATE CONSTRAINT publication_openalex_unique IF NOT EXISTS
        FOR (p:Publication) REQUIRE p.openalex_url IS UNIQUE;
        """,

        # Venue: Community-safe uniqueness via synthetic key
        # v.key = toLower(v.name) + '|' + toLower(v.type)
        """
        CREATE CONSTRAINT venue_key_unique IF NOT EXISTS
        FOR (v:Venue) REQUIRE v.key IS UNIQUE;
        """,

        # Institution: unique by OpenAlex institution URL
        """
        CREATE CONSTRAINT institution_openalex_unique IF NOT EXISTS
        FOR (i:Institution) REQUIRE i.openalex_url IS UNIQUE;
        """,

        # Department: unique name (from old script)
        """
        CREATE CONSTRAINT department_name_unique IF NOT EXISTS
        FOR (d:Department) REQUIRE d.department IS UNIQUE;
        """,

        # AnnualReport: unique aarId (from old script)
        """
        CREATE CONSTRAINT annual_report_name_unique IF NOT EXISTS
        FOR (a:AnnualReport) REQUIRE a.aarId IS UNIQUE;
        """,

        # Keyword: unique name (from old script)
        """
        CREATE CONSTRAINT keyword_name_unique IF NOT EXISTS
        FOR (k:Keyword) REQUIRE k.name IS UNIQUE;
        """,

        # Tag: unique name (from old script)
        """
        CREATE CONSTRAINT tag_unique IF NOT EXISTS
        FOR (t:Tag) REQUIRE t.name IS UNIQUE;
        """,

        # Helpful indexes
        """
        CREATE INDEX researcher_norm_idx IF NOT EXISTS FOR (r:Researcher) ON (r.normalized_name);
        """,
        """
        CREATE INDEX publication_doi_idx IF NOT EXISTS FOR (p:Publication) ON (p.doi);
        """,
        """
        CREATE INDEX institution_ror_idx IF NOT EXISTS FOR (i:Institution) ON (i.ror);
        """,
        # Optional: speed up Venue lookups by key
        """
        CREATE INDEX venue_key_idx IF NOT EXISTS FOR (v:Venue) ON (v.key);
        """,
    ]


def load_institutional_nodes_and_rels() -> list[str]:
    """Institutional (legacy) data: sys_users, departments, AAR, keywords, tags, subclusters."""
    return [
        # Researchers from sys_users.csv — MERGE by userId, keep OpenAlex URL property to unify with OpenAlex load
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///sys_users.csv' AS row
          WITH row
          WHERE row.user_id IS NOT NULL AND trim(row.user_id) <> ''
          MERGE (r:Researcher { userId: trim(row.user_id) })
          SET r.ccid     = CASE WHEN trim(coalesce(row.user_name,'')) = '' THEN NULL ELSE trim(row.user_name) END,
              r.firstName= CASE WHEN trim(coalesce(row.first_name,'')) = '' THEN NULL ELSE trim(row.first_name) END,
              r.lastName = CASE WHEN trim(coalesce(row.last_name,'')) = '' THEN NULL ELSE trim(row.last_name) END,
              r.email    = CASE WHEN row.email IS NULL OR trim(row.email) = '' THEN 'EmailCannotFound' ELSE trim(row.email) END,
              r.rank     = CASE WHEN trim(coalesce(row.rank,'')) = '' THEN NULL ELSE trim(row.rank) END,
              r.website  = CASE WHEN row.website IS NULL OR trim(row.website) = '' THEN 'WebsiteCannotFound' ELSE trim(row.website) END,
              r.active   = CASE WHEN trim(coalesce(row.active,'')) = '' THEN NULL ELSE trim(row.active) END,
              r.openalex_url = CASE WHEN trim(coalesce(row.authorID,'')) = '' THEN r.openalex_url ELSE trim(row.authorID) END,
              r.normalized_name = toLower(trim(coalesce(row.first_name,'') + ' ' + coalesce(row.last_name,'')))
        } IN TRANSACTIONS OF 1000 ROWS;
        """,
        # Department membership
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///sys_users.csv' AS row
          WITH row
          WHERE row.department IS NOT NULL AND trim(row.department) <> ''
            AND row.user_id IS NOT NULL AND trim(row.user_id) <> ''
          MERGE (r:Researcher { userId: trim(row.user_id) })
          MERGE (d:Department { department: trim(row.department) })
          MERGE (r)-[:BELONGS_TO]->(d)
        } IN TRANSACTIONS OF 2000 ROWS;
        """,
        # Annual Reports
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///academic_annual_reports.csv' AS aar
          WITH aar
          MATCH (n:Researcher { userId: aar.user_id })
          WHERE aar.annual_report_id IS NOT NULL AND trim(aar.annual_report_id) <> ''
          MERGE (a:AnnualReport { aarId: trim(aar.annual_report_id) })
          MERGE (n)-[:REPORTED]->(a)
        } IN TRANSACTIONS OF 2000 ROWS;
        """,
        # Research Keywords
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///research_keywords.csv' AS row
          WITH row
          MATCH (n:Researcher)-[:REPORTED]->(a:AnnualReport { aarId: row.annual_report_id })
          WHERE row.research_keyword IS NOT NULL AND trim(row.research_keyword) <> ''
          MERGE (k:Keyword { name: trim(row.research_keyword) })
          MERGE (n)-[:WORKS_ON]->(k)
        } IN TRANSACTIONS OF 2000 ROWS;
        """,
        # Research Tags + STUDIES
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///research_tags.csv' AS row
          WITH row
          MATCH (n:Researcher)-[:REPORTED]->(a:AnnualReport { aarId: row.annual_report_id })
          WHERE row.research_tag IS NOT NULL AND trim(row.research_tag) <> ''
          MERGE (t:Tag { name: trim(row.research_tag) })
          MERGE (a)-[:LABELED]->(t)
          MERGE (n)-[:STUDIES]->(t)
        } IN TRANSACTIONS OF 2000 ROWS;
        """,
        # Subclusters (Tag -> Subcategory -> MainCategory; Tag SUB_OF Subcategory or MainCategory)
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///11-all-subclusters.csv' AS row
          WITH row
          WHERE row.keyword IS NOT NULL AND trim(row.keyword) <> ''
            AND row.main_category IS NOT NULL AND trim(row.main_category) <> ''
          MERGE (t:Tag { name: trim(row.keyword) })
          FOREACH (_ IN CASE WHEN row.subcategory IS NOT NULL AND trim(row.subcategory) <> '' THEN [1] ELSE [] END |
            MERGE (s:Subcategory { name: trim(row.subcategory), main: trim(row.main_category) })
            MERGE (m:MainCategory { name: trim(row.main_category) })
            MERGE (s)-[:SUB_OF]->(m)
            MERGE (t)-[:SUB_OF]->(s)
          )
          FOREACH (_ IN CASE WHEN row.subcategory IS NULL OR trim(row.subcategory) = '' THEN [1] ELSE [] END |
            MERGE (m:MainCategory { name: trim(row.main_category) })
            MERGE (t)-[:SUB_OF]->(m)
          )
        } IN TRANSACTIONS OF 2000 ROWS;
        """,
    ]


def load_openalex_nodes() -> list[str]:
    """OpenAlex nodes from your generated CSVs: Researchers, Publications, Venues, Institutions."""
    return [
        # Researchers by openalex_url; merge onto existing sys_users via shared openalex_url
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///researchers_openalex.csv' AS row
          WITH row WHERE row.openalex_url IS NOT NULL AND trim(row.openalex_url) <> ''
          MERGE (r:Researcher { openalex_url: trim(row.openalex_url) })
          SET r.name            = CASE WHEN trim(coalesce(row.name,'')) = '' THEN r.name ELSE trim(row.name) END,
              r.normalized_name = CASE WHEN trim(coalesce(row.normalized_name,'')) = '' THEN r.normalized_name ELSE trim(row.normalized_name) END
        } IN TRANSACTIONS OF 2000 ROWS;
        """,
        # Publications
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///publications.csv' AS row
          WITH row
          MERGE (p:Publication { openalex_url: trim(row.openalex_url) })
          SET p.doi              = CASE WHEN trim(coalesce(row.doi,'')) = '' THEN NULL ELSE trim(row.doi) END,
              p.title            = CASE WHEN trim(coalesce(row.title,'')) = '' THEN NULL ELSE row.title END,
              p.cited_by_count   = toInteger(coalesce(row.cited_by_count, 0)),
              p.cited_by_url     = CASE WHEN trim(coalesce(row.cited_by_url,'')) = '' THEN NULL ELSE trim(row.cited_by_url) END,
              p.publication_year = CASE WHEN trim(coalesce(row.publication_year,'')) = '' THEN NULL ELSE toInteger(row.publication_year) END
        } IN TRANSACTIONS OF 2000 ROWS;
        """,
        # Venues (Community-safe: compute v.key and MERGE by it; keep original-casing on name/type)
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///venues.csv' AS row
          WITH row,
               trim(row.name) AS raw_name,
               CASE WHEN trim(coalesce(row.type,'')) = '' THEN 'Other' ELSE trim(row.type) END AS raw_type
          WITH row, raw_name, raw_type,
               toLower(raw_name) + '|' + toLower(raw_type) AS vkey
          MERGE (v:Venue { key: vkey })
          SET v.name = COALESCE(v.name, raw_name),
              v.type = COALESCE(v.type, raw_type)
        } IN TRANSACTIONS OF 2000 ROWS;
        """,
        # Institutions
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///institutions.csv' AS row
          WITH row
          MERGE (i:Institution { openalex_url: trim(row.openalex_url) })
          SET i.name         = CASE WHEN trim(coalesce(row.name,'')) = '' THEN NULL ELSE trim(row.name) END,
              i.ror          = CASE WHEN trim(coalesce(row.ror,''))  = '' THEN NULL ELSE trim(row.ror) END,
              i.country_code = CASE WHEN trim(coalesce(row.country_code,'')) = '' THEN NULL ELSE trim(row.country_code) END
        } IN TRANSACTIONS OF 2000 ROWS;
        """,
    ]


def load_openalex_relationships() -> list[str]:
    """OpenAlex relationships: authorship, published_in, coauthor edges, affiliations."""
    return [
        # Researcher -> Publication
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///authorship.csv' AS row
          WITH row
          MATCH (p:Publication { openalex_url: trim(row.publication_openalex_url) })
          MATCH (r:Researcher  { openalex_url: trim(row.researcher_openalex_url) })
          MERGE (r)-[:PUBLISHED]->(p)
        } IN TRANSACTIONS OF 5000 ROWS;
        """,
        # Publication -> Venue (match by synthetic key to avoid case mismatches)
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///publication_venue.csv' AS row
          WITH row,
               CASE WHEN trim(coalesce(row.venue_type,'')) = '' THEN 'Other' ELSE trim(row.venue_type) END AS vtype,
               toLower(trim(row.venue_name)) + '|' + toLower(
                 CASE WHEN trim(coalesce(row.venue_type,'')) = '' THEN 'Other' ELSE trim(row.venue_type) END
               ) AS vkey
          MATCH (p:Publication { openalex_url: trim(row.publication_openalex_url) })
          MATCH (v:Venue { key: vkey })
          MERGE (p)-[:PUBLISHED_IN]->(v)
        } IN TRANSACTIONS OF 5000 ROWS;
        """,
        # Co-author weighted undirected (a->b only when a<b)
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///coauthor_relationships.csv' AS row
          WITH row,
               CASE WHEN trim(row.researcher1_openalex_url) < trim(row.researcher2_openalex_url)
                    THEN [trim(row.researcher1_openalex_url), trim(row.researcher2_openalex_url)]
                    ELSE [trim(row.researcher2_openalex_url), trim(row.researcher1_openalex_url)]
               END AS pair,
               toInteger(coalesce(row.collaboration_count,0)) AS cnt
          MATCH (a:Researcher { openalex_url: pair[0] })
          MATCH (b:Researcher { openalex_url: pair[1] })
          MERGE (a)-[r:CO_AUTHOR_WITH]->(b)
          SET r.count = coalesce(r.count,0) + cnt
        } IN TRANSACTIONS OF 5000 ROWS;
        """,
        # Researcher -> Institution
        """
        CALL {
          LOAD CSV WITH HEADERS FROM 'file:///author_institution.csv' AS row
          WITH row
          MATCH (a:Researcher  { openalex_url: trim(row.author_openalex_url) })
          MATCH (i:Institution { openalex_url: trim(row.institution_openalex_url) })
          MERGE (a)-[:AFFILIATED_WITH]->(i)
        } IN TRANSACTIONS OF 5000 ROWS;
        """,
    ]


def main():
    parser = argparse.ArgumentParser(description="Rebuild Neo4j graph from institutional + OpenAlex CSVs (Community-safe).")
    parser.add_argument("--wipe", action="store_true", help="Drop constraints/indexes and delete all data before import.")
    parser.add_argument("--database", default=DEFAULT_DATABASE, help="Neo4j database name (Enterprise multi-db). Default: server default")
    args = parser.parse_args()

    # Connect
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        print(f"✅ Connected to Neo4j at {NEO4J_URI}")
        if args.database:
            print(f"   Using database: {args.database}")
    except Exception as e:
        print(f"❌ Failed to connect to Neo4j at {NEO4J_URI}: {e}")
        sys.exit(1)

    try:
        if args.wipe:
            wipe_database(driver, database=args.database)

        print("🏗️ Creating constraints and indexes...")
        exec_statements(driver, constraints_and_indexes(), database=args.database, label="constraints+indexes")

        print("🏛️ Loading institutional nodes & relationships (sys_users, departments, AAR, keywords, tags, subclusters)...")
        exec_statements(driver, load_institutional_nodes_and_rels(), database=args.database, label="institutional")

        print("📥 Loading OpenAlex nodes (Researcher, Publication, Venue, Institution)...")
        exec_statements(driver, load_openalex_nodes(), database=args.database, label="openalex-nodes")

        print("🔗 Loading OpenAlex relationships (PUBLISHED, PUBLISHED_IN, CO_AUTHOR_WITH, AFFILIATED_WITH)...")
        exec_statements(driver, load_openalex_relationships(), database=args.database, label="openalex-rels")

        print("🎉 Import complete!")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
