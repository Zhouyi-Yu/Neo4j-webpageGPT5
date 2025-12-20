# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [3.0.0] - 2025-12-20
### Added
- **FastAPI Migration**: Completely replaced Flask with FastAPI for high-performance, asynchronous request handling.
- **Asynchronous Pipeline**: Refactored Neo4j and OpenAI integrations to use `async/await` throughout.
- **Pydantic Validation**: Added strict request and response models for improved API stability.
- **Project Documentation**: Created comprehensive `README.md` and detailed system `walkthrough.md`.

### Changed
- **Strict Logic Parity**: Realigned the backend code to perfectly match the original scientific discovery logic from the production version.
- **Improved Author Discovery**: Re-implemented the dynamic LLM-driven Cypher generation for better semantic search results.

## [2.1.0] - 2024-12-18
### Added
- **Double Layer LLMs (Speculative Synthesis)**: Integrated parallel LLM calls to significantly reduce response latency.
- **Fuzzy Search Fallback**: Implemented Neo4j full-text indexes to handle typos and partial names in author resolution.

### Changed
- **Re-constructed UI**: Modernized the web interface with improved chat bubbles, debug panels, and responsiveness.

## [2.0.0] - 2024-Fall
### Added
- **Semantic Search**: Integrated OpenAI embeddings and Neo4j vector search to support topic-based queries.
- **Vector Indexing**: Built HNSW-based vector indexes for research publication abstracts.

## [1.0.0] - 2024-Summer-End
### Added
- **Initial Prototype**: Basic Q&A system using hardcoded Cypher templates and exact author name matching.
- **Flask Backend**: Standard synchronous API for research discovery.
- **Neo4j Core**: Initial publication graph database schema.

---
*Note: Version numbering prior to 3.0.0 is reconstructed based on project milestones.*
