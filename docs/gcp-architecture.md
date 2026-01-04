# GCP Production Architecture

## Infrastructure Overview

This document details the **Google Cloud Platform** deployment architecture for the Neo4j Research Q&A System.

## 🏗️ Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Google Cloud Platform                     │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐ │
│  │         Compute Engine (e2-medium, Ubuntu 22.04)       │ │
│  │                                                          │ │
│  │  ┌──────────────────┐      ┌─────────────────────────┐ │ │
│  │  │   FastAPI App    │      │   Neo4j 5.26 Enterprise │ │ │
│  │  │   (Port 5173)    │◄────►│   - Page Cache: 2GB     │ │ │
│  │  │                  │      │   - Heap: 1GB           │ │ │
│  │  │  - Async Pipeline│      │   - Bolt: 7687          │ │ │
│  │  │  - LLM Synthesis │      │   - Browser: 7474       │ │ │
│  │  └──────────────────┘      └─────────────────────────┘ │ │
│  │                                                          │ │
│  └────────────────────────────────────────────────────────┘ │
│                            │                                 │
│                            │ External Static IP              │
│  ┌────────────────────────▼──────────────────────────────┐ │
│  │              Firewall Rules (VPC Network)              │ │
│  │  - Allow TCP:7687 (Neo4j Bolt)                         │ │
│  │  - Allow TCP:7474 (Neo4j Browser)                      │ │
│  │  - Allow TCP:80/443 (HTTP/HTTPS)                       │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Internet
                              ▼
                    ┌──────────────────┐
                    │  Faculty Users   │
                    │  (Researchers)   │
                    └──────────────────┘
```

## 🔧 Deployment Specifications

### Compute Instance
- **Machine Type**: `e2-medium` (2 vCPUs, 4GB RAM)
- **OS**: Ubuntu 22.04 LTS
- **Zone**: `us-central1-a` (or your configured zone)
- **Disk**: 20GB SSD persistent disk

### Neo4j Configuration
```conf
# Optimized for 100k+ research nodes
server.memory.pagecache.size=2G
server.memory.heap.initial_size=1G
server.memory.heap.max_size=1G

# Network bindings
server.bolt.enabled=true
server.bolt.listen_address=0.0.0.0:7687
```

### Security Measures
1. **Authentication**: Neo4j native auth with strong passwords
2. **Firewall**: Restricted ingress rules (only necessary ports)
3. **Credentials**: Environment variable-based configuration (never hardcoded)
4. **API Keys**: OpenAI keys stored in `.env` (excluded from version control)

## 📊 Data Migration Process

The production database was populated via a full dump/restore:

```bash
# On local machine (export)
neo4j-admin database dump neo4j --to-path=/backup

# Transfer to GCP
gcloud compute scp neo4j.dump <instance-name>:/tmp/

# On GCP instance (restore)
sudo -u neo4j neo4j-admin database load neo4j --from-path=/tmp/ --overwrite-destination=true
```

### Verification
- **Node Count**: 100,000+ research papers, authors, and affiliations
- **Data Parity**: 100% match with local development database
- **Index Integrity**: All semantic search indices (HNSW) migrated successfully

## 🚀 Deployment Timeline

See [CHANGELOG.md](../CHANGELOG.md) Version 3.1.0 for the complete deployment story:
- Neo4j 5.26 installation and tuning
- Data migration and verification
- Frontend connectivity testing
- Production handoff to Faculty of Engineering

## 🔗 External Access

The system is accessible via the GCP external IP (redacted for security). Faculty members connect using:
- **Web App**: `http://<EXTERNAL_IP>:5173`
- **Neo4j Browser**: `http://<EXTERNAL_IP>:7474`

## 📈 Performance Metrics

Post-migration benchmarks:
- **Average Query Latency**: <20 seconds (including LLM synthesis)
- **Semantic Search**: <500ms for top-k retrieval
- **Concurrent Users**: Supports 5-10 simultaneous research queries
