<div align="center">

# 🤖 Enterprise AI Assistant

**Production-grade, secure, multi-tenant Autonomous AI platform powered by LangGraph, Enterprise RAG, and Human-in-the-Loop Orchestration.**

[![Next.js](https://img.shields.io/badge/Next.js-16.3.4-black?style=for-the-badge&logo=next.js)](https://nextjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15%20%2B%20pgvector-336791?style=for-the-badge&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic%20AI-orange?style=for-the-badge)](https://www.langchain.com/langgraph)
[![Redis](https://img.shields.io/badge/Redis-7%20Alpine-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Multi--Stage-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-180%20Passed%20(100%25)-success?style=for-the-badge&logo=pytest&logoColor=white)](backend/tests/)

[Live Local App](http://localhost:3000) • [Swagger API Docs](http://localhost:8000/docs) • [Architecture](#-system-architecture) • [Features](#-core-features) • [Quickstart](#-quickstart-guide) • [Docker](#-docker-deployment)

</div>

---

## 🌟 Overview

**Enterprise AI Assistant** is an end-to-end, enterprise-ready artificial intelligence platform designed to securely connect corporate knowledge bases with cutting-edge LLMs (Gemini / OpenAI). It features stateful agent workflows via **LangGraph**, robust **Human-in-the-Loop (HITL)** governance, strict multi-tenant isolation, and a comprehensive AI observability suite.

---

## 🏛️ System Architecture

```
                                  ┌─────────────────────────────────────────┐
                                  │       Next.js 16 Client (App Router)    │
                                  │   TailwindCSS • Lucide • SSE Stream     │
                                  └────────────────────┬────────────────────┘
                                                       │ HTTPS / SSE
                                                       ▼
                                  ┌─────────────────────────────────────────┐
                                  │           FastAPI Gateway               │
                                  │     Uvicorn • Python 3.11 • JWT RBAC    │
                                  └───────┬─────────────────────────┬───────┘
                                          │                         │
                   ┌──────────────────────┴──────┐           ┌──────┴──────────────────────┐
                   │    PostgreSQL 15 + pgvector │           │       Redis 7 (Alpine)      │
                   │    HNSW Cosine Vector Index │           │   Sliding-Window Limiter    │
                   │    Row-Level Tenant Isolation│           │   In-Memory Fallback Guard │
                   └──────────────┬──────────────┘           └─────────────────────────────┘
                                  │
         ┌────────────────────────┴────────────────────────┬────────────────────────┐
         │                                                 │                        │
         ▼                                                 ▼                        ▼
┌──────────────────┐                             ┌──────────────────┐     ┌──────────────────┐
│  Enterprise RAG  │                             │ LangGraph Agent  │     │ Workflow Engine  │
│ Hybrid Retrieval │                             │ Intent Routing   │     │ Multi-Step DAG   │
│ Reciprocal Rank  │                             │ Controlled Tools │     │ State Machine    │
│ Fusion (RRF)     │                             │ HITL Pause/Resume│     │ Step Approvals   │
└──────────────────┘                             └──────────────────┘     └──────────────────┘
```

---

## ✨ Core Features

### 1. 💬 Real-Time Streaming Assistant
- **Server-Sent Events (SSE)**: Ultra-low latency token-by-token streaming response delivery.
- **LangGraph Orchestration**: Automatic intent classification routing between direct conversation, hybrid knowledge retrieval, and controlled tool execution.
- **Grounded Responses**: Citations and source references attached directly to retrieved facts.

### 2. 📚 Enterprise Knowledge & Hybrid RAG
- **Multi-Format Ingestion**: Ingest and process `.pdf`, `.docx`, and `.txt` documents.
- **pgvector HNSW Indexing**: High-dimensional vector embeddings with cosine similarity distance search.
- **Hybrid Fusion (RRF)**: Merges dense vector semantic search with full-text keyword ranking to avoid hallucinations.
- **Tenant Scoping**: All document chunks and embeddings are hard-isolated by `organization_id`.

### 3. 🛠️ Controlled Safe Tools & Registry
- **Type-Safe Validation**: Pydantic v2 input/output schema enforcement.
- **Built-in Safe Tools**:
  - `calculator`: AST-evaluated mathematical calculation with zero `eval()` vulnerabilities.
  - `knowledge_search`: Internal organizational RAG knowledge querying.
  - `organization_stats`: Aggregated metrics with tenant scoping.
  - `create_demo_note`: Demonstrates Human-in-the-Loop sensitive action interception.
- **Role-Based Access Control**: Each tool declares minimum permitted roles (`VIEWER`, `MEMBER`, `MANAGER`, `ADMIN`, `OWNER`).

### 4. 🛡️ Human-in-the-Loop (HITL) Approval Engine
- **Segregation of Duties**: Requesters cannot self-approve sensitive operations.
- **State Machine**: Reversible pause/resume execution lifecycle (`PENDING` → `APPROVED` / `REJECTED` / `EXPIRED`).
- **Audit Logging**: Comprehensive structured audit log capturing all approval decisions.

### 5. ⚡ Stateful Workflow Engine
- **DAG Execution**: Define multi-step workflows combining tools, RAG queries, and LLM steps.
- **Conditional Branching & Safe Expressions**: Branch on upstream step results using sandboxed condition evaluators.
- **Graceful Pausing**: Steps tagged with `requires_approval=True` automatically pause execution until approved.

### 6. 📊 AI Evaluation & Observability Suite
- **Benchmarking Engine**: Automatic evaluation of precision, recall, F1 score, context groundedness, and citation attribution.
- **Trace & Latency Metrics**: Real-time p50, p95, and p99 latency tracking, token usage estimation, and categorized error tracking.
- **Data Redaction**: Automatic masking of passwords, Bearer tokens, and sensitive API secrets from telemetry.

---

## 🖥️ UI Tour & Application Routes

| Route | View | Description |
|---|---|---|
| `/assistant` | **AI Assistant** | Real-time streaming conversation, citation preview, and tool execution feedback. |
| `/documents` | **Document Center** | Upload corporate policies, monitor extraction/chunking status, and inspect indexed documents. |
| `/workflows` | **Workflows** | Interactive workflow builder, execution tracker, step inspection, and runtime logs. |
| `/approvals` | **HITL Approvals** | Dedicated governance queue for administrators to inspect, approve, or reject pending agent actions. |
| `/observability` | **Observability** | Live operational metrics dashboard: request rates, error distributions, token consumption, and latencies. |
| `/evaluations` | **Evaluations** | Benchmark runs and accuracy scoreboards for RAG and agent responses. |
| `/members` | **Organization** | Role management (`OWNER`, `ADMIN`, `MANAGER`, `MEMBER`, `VIEWER`) and team invitations. |
| `/login` / `/register` | **Authentication** | Secure JWT-based user onboarding with automated organization bootstrapping. |

---

## 🚀 Quickstart Guide

### Prerequisites
- **Python 3.11+**
- **Node.js 20+** & **npm**
- **PostgreSQL 15+** with `pgvector` extension
- **Redis 7+** (Optional: falls back to in-memory limiter)

---

### Method A: Docker Compose (Recommended for Production)

Run the complete production-configured stack with a single command:

```bash
# 1. Clone the repository
git clone https://github.com/taslimzafar/Enterprise-Ai-Assistant.git
cd Enterprise-Ai-Assistant

# 2. Configure environment
cp .env.example .env

# 3. Launch with Docker Compose
docker-compose -f docker-compose.prod.yml up -d --build
```

Access the services:
- **Frontend App**: [http://localhost:3000](http://localhost:3000)
- **FastAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

### Method B: Local Development Setup

#### 1. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start FastAPI development server
uvicorn app.main:app --reload --port 8000
```

#### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start Next.js development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## ⚙️ Environment Configuration

Refer to [`.env.example`](.env.example) for a complete template.

| Variable | Description | Default / Example |
|---|---|---|
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://postgres:postgres@localhost:5432/enterprise_ai` |
| `REDIS_URL` | Redis cache and rate limiting URL | `redis://localhost:6379/0` |
| `REDIS_ENABLED` | Toggle Redis integration (`true`/`false`) | `true` |
| `SECRET_KEY` | 64+ char cryptographic key for JWT tokens | `openssl rand -hex 32` |
| `BACKEND_CORS_ORIGINS` | Permitted frontend origins | `["http://localhost:3000"]` |
| `STORAGE_BACKEND` | Storage provider (`local` or `s3`) | `local` |
| `S3_BUCKET_NAME` | S3 / MinIO storage bucket name | `enterprise-ai-documents` |
| `GEMINI_API_KEY` | Google Gemini API Key | `AIzaSy...` |
| `OPENAI_API_KEY` | OpenAI API Key (Optional) | `sk-...` |
| `OBSERVABILITY_ENABLED` | Enable telemetry & request tracing | `true` |

---

## 🧪 Testing & Verification

The repository includes a comprehensive 180-test automated suite covering all application layers:

```bash
# Run complete test suite (180 tests)
cd backend
python -m pytest -v

# Run production smoke test suite (12 operational subsystems)
python -m pytest tests/test_smoke.py -v

# Verify Alembic database migrations
alembic check

# Build Next.js frontend
cd ../frontend
npm run build
```

### Smoke Test Verification Coverage
- [x] Liveness (`/health`) & Readiness (`/ready`)
- [x] User Registration & JWT Authentication
- [x] Multi-Tenant Organization Isolation
- [x] RBAC Permissions Enforcement
- [x] Document Ingestion, Magic Bytes Inspection & Storage
- [x] Hybrid Vector RAG Retrieval & Citations
- [x] Streaming Conversation Initiation
- [x] Controlled Tool Execution (Calculator)
- [x] HITL Approval Creation & Segregation of Duties
- [x] Workflow Engine Step Execution & Branching
- [x] AI Observability & Evaluation Metrics

---

## 🔒 Security & Hardening Highlights

- **Non-Root Containers**: Both frontend and backend Dockerfiles execute as unprivileged users (`appuser:10001` / `nextjs:1001`).
- **Security Headers**: HSTS, Content-Security-Policy (CSP), X-Frame-Options: `DENY`, X-Content-Type-Options: `nosniff`.
- **Upload Hardening**: File magic-bytes signature verification, path traversal sanitation, and file size limits.
- **Dynamic Rate Limiter**: Sliding-window rate limiting per tenant/user with zero-downtime memory fallback.
- **Strict Tenant Isolation**: All database queries strictly join and filter on `organization_id`.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
