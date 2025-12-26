# Neo4j RAG System - Cloud Deployment Guide

Complete step-by-step instructions for deploying to GCP Cloud Run, AWS App Runner, or Azure Container Apps.

---

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Cloud VM Setup (Oracle Cloud - Recommended)](#cloud-vm-setup)
3. [GCP Compute Engine Setup](#gcp-vm-setup)
4. [CI/CD with GitHub Actions](#cicd-setup)
5. [Database migration (4GB+)](#db-migration)
6. [Local Testing with Docker](#local-testing)

---

## Prerequisites

### Required Tools
```bash
# Install Docker
# Mac: Download from https://www.docker.com/products/docker-desktop
# Verify installation
docker --version

# Install Cloud CLI (choose one based on your target cloud)
# Google Cloud
brew install --cask google-cloud-sdk

# AWS
brew install awscli

# Azure
brew install azure-cli
```

### Required Accounts
- [ ] Docker Hub account (free): https://hub.docker.com/signup
- [ ] Neo4j Aura account (free tier): https://neo4j.com/cloud/aura/
- [ ] OpenAI API key: https://platform.openai.com/api-keys
- [ ] Cloud provider account (GCP/AWS/Azure)

---

## Database Setup (Neo4j AuraDB)

**Why AuraDB?** Your Docker Compose setup uses a local Neo4j container, but for production you need a managed database that's always on.

### Step 1: Create Free Neo4j AuraDB Instance

1. Go to https://console.neo4j.io/
2. Click **"Create Instance"** → **"AuraDB Free"**
3. Configure:
   - **Instance name:** `rag-research-db`
   - **Region:** Choose closest to your app (e.g., `us-east-1`)
   - **Database size:** Free (1GB)
4. Click **"Create"**
5. **IMPORTANT:** Save the credentials shown:
   ```
   Connection URI: neo4j+s://xxxxx.databases.neo4j.io
   Username: neo4j
   Password: [generated password - SAVE THIS!]
   ```

### Step 2: Load Your Data

**Option A: Using Neo4j Browser (GUI)**
1. Click **"Open"** on your AuraDB instance
2. Login with credentials from Step 1
3. Run your data import Cypher scripts

**Option B: Using Python Script**
```python
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
```

---

## Local Testing with Docker

Before deploying, verify everything works locally.

### Step 1: Create `.env` File
```bash
cd /Users/jookenblue/Desktop/ZhouyiPortofolio/Neo4j-webpageGPT5
cat > .env << 'EOF'
# Neo4j AuraDB (from Database Setup)
NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-auradb-password

# OpenAI
OPENAI_API_KEY=sk-proj-xxxxx

# Session Secret (generate with: openssl rand -hex 32)
SESSION_SECRET_KEY=your-secret-key-here
EOF
```

### Step 2: Build and Test
```bash
# Build the Docker image
docker build -t neo4j-rag:latest .

# Run locally (connected to AuraDB)
docker run -p 8000:8000 --env-file .env neo4j-rag:latest

# Test in browser
open http://localhost:8000
```

**Expected Result:** 
- Website loads with chat interface
- Queries return answers (connected to AuraDB)
- Debug panel shows Cypher queries

---

## Deploy to GCP Cloud Run

**Best for:** Serverless, auto-scaling, pay-per-request

### Step 1: Setup GCP Project

```bash
# Login to GCP
gcloud auth login

# Create new project (or use existing)
gcloud projects create rag-system-prod --name="RAG System"

# Set active project
gcloud config set project rag-system-prod

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  containerregistry.googleapis.com \
  cloudbuild.googleapis.com
```

### Step 2: Build and Push Docker Image

```bash
# Navigate to project
cd /Users/jookenblue/Desktop/ZhouyiPortofolio/Neo4j-webpageGPT5

# Configure Docker for GCP
gcloud auth configure-docker

# Build and tag image
docker build -t gcr.io/rag-system-prod/neo4j-rag:v1 .

# Push to Google Container Registry
docker push gcr.io/rag-system-prod/neo4j-rag:v1
```

### Step 3: Create Secret Manager Entries

```bash
# Store sensitive values in Secret Manager (more secure than env vars)
echo -n "your-openai-key" | gcloud secrets create openai-api-key --data-file=-
echo -n "your-neo4j-password" | gcloud secrets create neo4j-password --data-file=-
echo -n "$(openssl rand -hex 32)" | gcloud secrets create session-secret --data-file=-
```

### Step 4: Deploy to Cloud Run

**Option A: Using gcloud CLI**
```bash
gcloud run deploy neo4j-rag \
  --image gcr.io/rag-system-prod/neo4j-rag:v1 \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars="NEO4J_URI=neo4j+s://xxxxx.databases.neo4j.io,NEO4J_USER=neo4j" \
  --set-secrets="NEO4J_PASSWORD=neo4j-password:latest,OPENAI_API_KEY=openai-api-key:latest,SESSION_SECRET_KEY=session-secret:latest" \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --concurrency 80
```

**Option B: Using YAML Config**
```bash
# Update deployment/gcp/service.yaml with your image
# Then deploy:
gcloud run services replace deployment/gcp/service.yaml --region us-central1
```

### Step 5: Get Your Live URL
```bash
gcloud run services describe neo4j-rag --region us-central1 --format='value(status.url)'
```

**Output:** `https://neo4j-rag-xxxxx-uc.a.run.app`

---

## Deploy to AWS App Runner

**Best for:** AWS-native deployments, integrated with AWS services

### Step 1: Setup AWS

```bash
# Configure AWS CLI
aws configure
# Enter: Access Key ID, Secret Access Key, Region (us-east-1)

# Create ECR repository
aws ecr create-repository --repository-name neo4j-rag --region us-east-1
```

### Step 2: Push Image to ECR

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Tag image
docker tag neo4j-rag:latest YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/neo4j-rag:v1

# Push
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/neo4j-rag:v1
```

### Step 3: Create App Runner Service

```bash
# Create service using AWS Console (easier for first time)
# OR using CLI:

aws apprunner create-service \
  --service-name neo4j-rag \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/neo4j-rag:v1",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "8000",
        "RuntimeEnvironmentVariables": {
          "NEO4J_URI": "neo4j+s://xxxxx.databases.neo4j.io",
          "NEO4J_USER": "neo4j",
          "NEO4J_PASSWORD": "your-password",
          "OPENAI_API_KEY": "your-key"
        }
      }
    },
    "AutoDeploymentsEnabled": false
  }' \
  --instance-configuration '{
    "Cpu": "2 vCPU",
    "Memory": "4 GB"
  }' \
  --region us-east-1
```

**Get URL:**
```bash
aws apprunner describe-service --service-arn YOUR_SERVICE_ARN | grep ServiceUrl
```

---

## Deploy to Azure Container Apps

**Best for:** Microsoft ecosystem, hybrid cloud

### Step 1: Setup Azure

```bash
# Login
az login

# Create resource group
az group create --name rag-system-rg --location eastus

# Create container registry
az acr create --resource-group rag-system-rg --name ragsystemacr --sku Basic

# Create Container Apps environment
az containerapp env create \
  --name rag-env \
  --resource-group rag-system-rg \
  --location eastus
```

### Step 2: Push Image to Azure Container Registry

```bash
# Login to ACR
az acr login --name ragsystemacr

# Tag image
docker tag neo4j-rag:latest ragsystemacr.azurecr.io/neo4j-rag:v1

# Push
docker push ragsystemacr.azurecr.io/neo4j-rag:v1
```

### Step 3: Deploy Container App

```bash
az containerapp create \
  --name neo4j-rag \
  --resource-group rag-system-rg \
  --environment rag-env \
  --image ragsystemacr.azurecr.io/neo4j-rag:v1 \
  --target-port 8000 \
  --ingress external \
  --cpu 2 --memory 4Gi \
  --env-vars \
    NEO4J_URI="neo4j+s://xxxxx.databases.neo4j.io" \
    NEO4J_USER="neo4j" \
    NEO4J_PASSWORD="your-password" \
    OPENAI_API_KEY="your-key"
```

**Get URL:**
```bash
az containerapp show --name neo4j-rag --resource-group rag-system-rg --query properties.configuration.ingress.fqdn
```

---

## Post-Deployment

### Step 1: Test Your Live App

```bash
# Replace with your actual URL
LIVE_URL="https://neo4j-rag-xxxxx-uc.a.run.app"

# Test health
curl $LIVE_URL

# Test query endpoint
curl -X POST $LIVE_URL/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Who works on smart grids at UAlberta?"}'
```

### Step 2: Monitor Logs

**GCP:**
```bash
gcloud run services logs read neo4j-rag --region us-central1
```

**AWS:**
```bash
aws logs tail /aws/apprunner/neo4j-rag --follow
```

**Azure:**
```bash
az containerapp logs show --name neo4j-rag --resource-group rag-system-rg
```

### Step 3: Enable HTTPS & Custom Domain (Optional)

**GCP Cloud Run:**
- Automatic HTTPS ✅ (already enabled)
- Custom domain: https://cloud.google.com/run/docs/mapping-custom-domains

**AWS App Runner:**
- Automatic HTTPS ✅
- Custom domain: Console → Custom domains → Add

**Azure:**
- Automatic HTTPS ✅
- Custom domain: `az containerapp hostname add`

---

## Cost Estimates (Free Tier Eligible)

| Cloud | Free Tier | Typical Monthly Cost |
|-------|-----------|---------------------|
| **GCP Cloud Run** | 2M requests/month | $0 - $5 (light usage) |
| **AWS App Runner** | None (but cheap) | $5 - $15 |
| **Azure Container Apps** | 180,000 requests | $0 - $10 |
| **Neo4j AuraDB Free** | Forever free | $0 |

---

## Troubleshooting

### ❌ "Connection refused" to Neo4j
**Fix:** Check `NEO4J_URI` uses `neo4j+s://` (secured) not `bolt://`

### ❌ "OpenAI API key invalid"
**Fix:** Regenerate key at https://platform.openai.com/api-keys

### ❌ "Container failed to start"
**Fix:** Check logs for errors. Usually missing env vars.

### ❌ "Timeout" errors
**Fix:** Increase timeout in Cloud Run: `--timeout 300`

---

## Quick Reference

### Update Deployment (After Code Changes)

```bash
# 1. Rebuild image
docker build -t gcr.io/rag-system-prod/neo4j-rag:v2 .

# 2. Push
docker push gcr.io/rag-system-prod/neo4j-rag:v2

# 3. Redeploy (GCP example)
gcloud run deploy neo4j-rag \
  --image gcr.io/rag-system-prod/neo4j-rag:v2 \
  --region us-central1
```

### Rollback to Previous Version

```bash
gcloud run deploy neo4j-rag \
  --image gcr.io/rag-system-prod/neo4j-rag:v1 \
  --region us-central1
```

---

## Security Best Practices

✅ **Do:**
- Use Secret Manager for API keys (not env vars)
- Enable HTTPS only
- Restrict Neo4j firewall to your app's IP
- Use `.gitignore` for `.env` files

❌ **Don't:**
- Commit API keys to GitHub
- Use `--allow-unauthenticated` for internal apps
- Expose Neo4j browser publicly

---

## Next Steps

1. ✅ Deploy to **one** cloud (start with GCP - easiest)
2. 📊 Monitor for 24 hours, check logs
3. 🔗 Add live URL to your portfolio: `https://zhouyi-yu.github.io`
4. 📝 Update resume with "Deployed production RAG system to GCP Cloud Run"
5. 🎥 Record demo video showing live cloud deployment

---

**Questions?** Check deployment logs first:
- GCP: `gcloud run services logs read neo4j-rag`
- Issues: Open GitHub issue or check Stack Overflow

**Estimated Deployment Time:** 30-45 minutes (first time)

---

## Cloud VM Setup (Oracle Cloud - Recommended)

Oracle Cloud's "Always Free" tier is the best option for your 4GB database because it provides 24GB of RAM.

1.  **Sign up:** [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/).
2.  **Create Instance:**
    *   **Image:** Ubuntu 22.04 or 24.04.
    *   **Shape:** `VM.Standard.A1.Flex` (ARM-based).
    *   **Resources:** 4 OCPUs, 24GB RAM.
    *   **Networking:** Assign a Public IP and open ports `8000`, `7474`, `7687` in the VCN Security List.
3.  **SSH into VM:**
    ```bash
    ssh -i your-key.key ubuntu@your-vm-ip
    ```
4.  **Install Docker:**
    ```bash
    sudo apt update && sudo apt install -y docker.io docker-compose-v2
    sudo usermod -aG docker $USER
    # Log out and log back in for changes to take effect
    ```

---

## CI/CD with GitHub Actions

Automate your deployment so every `git push` updates your website.

### 1. GitHub Secrets
In your GitHub Repo: **Settings > Secrets and variables > Actions**, add:
*   `VM_IP`: Your VM Public IP.
*   `VM_USER`: `ubuntu` (for Oracle) or your GCP username.
*   `VM_SSH_KEY`: The contents of your private SSH key (`~/.ssh/id_rsa`).
*   `NEO4J_PASSWORD`: Your database password.
*   `OPENAI_API_KEY`: Your OpenAI key.
*   `SESSION_SECRET_KEY`: A random string for sessions.

### 2. How it works
The `.github/workflows/deploy.yml` file will:
1. Build your Docker image.
2. Push it to **GitHub Container Registry (GHCR)**.
3. SSH into your VM and run `docker compose up -d`.

---

## Database Migration (4GB+)

Since your database is 4GB, we don't put it in Docker. We upload the dump manually once.

1.  **Upload Dump to VM:**
    ```bash
    scp ./neo4j.dump ubuntu@your-vm-ip:~/neo4j.dump
    ```
2.  **Restore on VM:**
    ```bash
    # Create directory for Neo4j
    mkdir -p ~/neo4j-rag/backups
    mv ~/neo4j.dump ~/neo4j-rag/backups/neo4j.dump
    cd ~/neo4j-rag

    # Run the load command
    docker run --rm \
      -v $(pwd)/data:/data \
      -v $(pwd)/backups:/backups \
      neo4j:5.22.0 \
      neo4j-admin database load neo4j --from-path=/backups
    ```
3.  **Start Services:**
    ```bash
    docker compose -f docker-compose.prod.yml up -d
    ```

---
