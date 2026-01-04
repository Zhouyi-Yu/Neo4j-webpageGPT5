# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [4.1.0] - 2026-01-03
### Added
- **Speculative Parallel Synthesis**: Parallelized intent classification, embeddings, and Cypher generation to reduce latency by 60%.
- **Enhanced Debug Infrastructure**: Added a real-time "Latency Breakdown" panel to the UI, measuring every stage of the RAG pipeline.
- **Canonical Identity Resolution**: Implemented a secondary resolution layer that corrects typos (e.g., "Mark Reformt" -> "Marek Reformat") using database ground truth.
- **Improved UI Branding**: Relocated and scaled the Faculty of Engineering logo for a professional, distraction-free demo layout.

## [4.0.0] - 2025-12-30
### Added
- **Production Cloud Deployment**: Deployed full system to Google Cloud Platform (GCP) Compute Engine.
- **CI/CD Pipeline**: Implemented automated GitHub Actions workflow for zero-downtime SSH deployments.
- **Neo4j Enterprise**: Upgraded to Neo4j Enterprise Edition to support high-performance "Block Format" databases.
- **Infrastructure Code**: Added `docker-compose.prod.yml` and `DEPLOYMENT_GUIDE.md` for reproducible cloud setups.

### Changed
- **Database Architecture**: Migrated from local desktop DB to containerized 50GB+ cloud storage solution.
- **Memory Optimization**: Tuned JVM heap and pagecache settings for 8GB RAM cloud environment.

## [3.1.0] - 2025-12-28
### Added
- **Production Cloud Deployment**: Successfully deployed the entire Neo4j Enterprise stack to Google Cloud Platform (GCP).
  - Engineered a robust data migration strategy (handling version mismatches by upgrading from Neo4j 5.22 to 5.26).
  - Configured secure Docker environment variables and resolved GCP firewall networking issues for external access.
  - Demonstrated end-to-end cloud infrastructure management skills.
- **Improved Frontend**:
  - Fixed Control Flow Graph (CFG) visualization link.
  - Cleaned up UI logs for a more professional user experience.

## [3.0.0] - 2025-12-20
### Added
- **FastAPI Migration**: Completely replaced Flask with FastAPI for high-performance, asynchronous request handling.
- **Asynchronous Pipeline**: Refactored Neo4j and OpenAI integrations to use `async/await` throughout.
- **Pydantic Validation**: Added strict request and response models for improved API stability.
- **React Frontend**: Added a modern, responsive web interface with chat bubbles, debug panels, and improved user experience.
- **Project Documentation**: Created comprehensive `README.md` and detailed system `walkthrough.md`.

## [2.1.0] - 2025-12-18
### Added
- **Double Layer LLMs (Speculative Synthesis)**: Integrated parallel LLM calls to significantly reduce response latency.
- **Fuzzy Search Fallback**: Implemented Neo4j full-text indexes to handle typos and partial names in author resolution.

### Changed
- **Re-constructed UI**: Modernized the web interface with improved chat bubbles, debug panels, and responsiveness.

## [2.0.0] - 2025-Fall
### Added
- **Semantic Search**: Integrated OpenAI embeddings and Neo4j vector search to support topic-based queries.
- **Vector Indexing**: Built HNSW-based vector indexes for research publication abstracts.

## [1.0.0] - 2025-Summer-End
### Added
- **Initial Prototype**: Basic Q&A system using hardcoded Cypher templates and exact author name matching.
- **Flask Backend**: Standard synchronous API for research discovery.
- **Neo4j Core**: Initial publication graph database schema.

---
*Note: Version numbering prior to 3.0.0 is reconstructed based on project milestones.*
