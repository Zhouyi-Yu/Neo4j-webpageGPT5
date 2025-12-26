# Multi-Cloud Deployment Guide

You have asked to deploy to GCP, AWS, and Azure. This is an excellent way to demonstrate "Cloud Agnostic" design patterns.

## ⚠️ Architecture Note: Database Persistence
Running a stateful database like **Neo4j** inside a stateless container service (like Cloud Run or App Runner) is **not recommended** because you will lose your data every time the container restarts.

**Recommended Production Architecture:**
1.  **Database:** Use **Neo4j AuraDB (Free Tier)** as a managed service.
    *   You get a connection URI like `neo4j+s://xxxx.databases.neo4j.io`.
    *   You don't need to deploy a Neo4j container; you just connect to this URL.
2.  **Application:** Deploy *only* your FastAPI Python app container to the cloud providers.

---

## 1. Google Cloud Platform (GCP) - Cloud Run
**Service:** Cloud Run (Serverless containers)
**Why:** Easiest to deploy, scales to zero (costs $0 when not used).

**Deployment Steps:**
1.  **Build:** `gcloud builds submit --tag gcr.io/PROJECT_ID/neo4j-rag-app`
2.  **Deploy:**
    ```bash
    gcloud run deploy neo4j-rag-app \
      --image gcr.io/PROJECT_ID/neo4j-rag-app \
      --set-env-vars NEO4J_URI=neo4j+s://xxx,NEO4J_PASSWORD=xxx,OPENAI_API_KEY=xxx \
      --platform managed
    ```

## 2. AWS - App Runner
**Service:** AWS App Runner (Managed container service)
**Why:** Easier than ECS/Fargate for simple web apps.

**Deployment Steps:**
1.  **Push** your image to Amazon ECR (Elastic Container Registry).
2.  **Create Service** in App Runner console pointing to that ECR image.
3.  **Variables:** Add `NEO4J_URI`, etc., in the configuration console.

## 3. Microsoft Azure - Container Apps
**Service:** Azure Container Apps
**Why:** Modern serverless container platform.

**Deployment Steps:**
1.  **Push** to Azure Container Registry (ACR).
2.  **Deploy:**
    ```bash
    az containerapp up \
      --name neo4j-rag-app \
      --resource-group my-group \
      --image myregistry.azurecr.io/neo4j-rag-app \
      --env-vars NEO4J_URI=neo4j+s://xxx ...
    ```
