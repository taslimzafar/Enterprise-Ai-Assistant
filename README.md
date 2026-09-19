# Enterprise AI Assistant

An enterprise-grade, multi-tenant AI Assistant platform featuring Retrieval-Augmented Generation (RAG), LangGraph autonomous agent execution, controlled tool calling, Human-in-the-Loop (HITL) approvals, a multi-step workflow engine, comprehensive security hardening, and an automated evaluation and observability layer.

---

## 1. System Architecture

The application is structured into isolated, scalable service tiers:

```
                      ┌───────────────────────────────┐
                      │    Next.js 16 (App Router)    │
                      │    TailwindCSS / TypeScript   │
                      └───────────────┬───────────────┘
                                      │  HTTPS / SSE
                                      ▼
                      ┌───────────────────────────────┐
                      │      FastAPI (Uvicorn)        │
                      │  Async Python 3.11 Backend    │
                      └───────┬───────────────┬───────┘
                              │               │
            ┌─────────────────┴────┐     ┌────┴─────────────────┐
            │ PostgreSQL+pgvector  │     │   Redis 7 (Alpine)   │
            │  Multi-tenant Store  │     │ Caching & Rate Limit │
            └──────────────────────┘     └──────────────────────┘
                              │
            ┌─────────────────┴────────────────────────┐
            │  Document Storage (S3 / MinIO / Local)   │
            │  Tenant-isolated document ingestion      │
            └──────────────────────────────────────────┘
```

### Core Subsystems
- **Multi-Tenancy & RBAC**: Tenant isolation enforced at database query level (`organization_id`). Strict role hierarchy: `OWNER` > `ADMIN` > `MANAGER` > `MEMBER` > `VIEWER`.
- **Enterprise RAG**: Document parsing (PDF, DOCX, TXT), chunking, hybrid vector search (pgvector `HNSW` cosine similarity) combined with keyword search via Reciprocal Rank Fusion (`RRF`).
- **LangGraph Agent**: Stateful graph orchestration directing queries between conversational responses, RAG retrieval, and controlled tool calls.
- **Controlled Tools**: Sandboxed tools (`calculator`, `knowledge_search`, `organization_stats`, `create_demo_note`) with Pydantic schema validation, timeout limits, and RBAC authorization.
- **HITL Approval Engine**: Segregation of duties pausing sensitive operations pending manual review by authorized personnel (`ADMIN`/`OWNER`).
- **Stateful Workflow Engine**: Multi-step DAG state machines supporting conditional branching, retries, and step-level approval integration.
- **Security Hardening**: Sliding-window rate limiter, HTTP security headers (`CSP`, `X-Content-Type-Options`, `X-Frame-Options`), magic bytes inspection, path traversal protection, AST expression safety, and automatic secret redaction.
- **AI Evaluation & Observability**: Deterministic evaluators for retrieval precision/recall, context groundedness, answer correctness, and p50/p95/p99 latency percentiles.

---

## 2. Environment Configuration

Copy `.env.example` to `.env` and configure your settings:

```bash
cp .env.example .env
```

### Key Environment Variables

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `ENVIRONMENT` | Runtime mode (`production`, `development`) | `production` |
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://postgres:pass@localhost:5432/enterprise_ai` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `JWT_SECRET` | 64+ char cryptographic secret for JWTs | Run `openssl rand -hex 32` |
| `BACKEND_CORS_ORIGINS` | JSON list of trusted web origins | `["http://localhost:3000"]` |
| `LLM_PROVIDER` | LLM provider choice (`gemini`, `openai`) | `gemini` |
| `GEMINI_API_KEY` | Google Gemini API Key | `AIzaSy...` |
| `STORAGE_BACKEND` | Storage type (`local` or `s3`) | `local` |
| `S3_BUCKET_NAME` | Cloud storage bucket name | `enterprise-ai-documents` |

---

## 3. Local Development Setup

### Backend

```bash
cd backend
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```
Access the application UI at `http://localhost:3000` and API documentation at `http://localhost:8000/api/v1/docs`.

---

## 4. Docker Deployment

### Production Docker Compose

To start the full production stack (PostgreSQL + pgvector, Redis, Backend, and Frontend):

```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

### Standalone Docker Containers

**Build Backend:**
```bash
docker build -t enterprise-ai-backend:latest ./backend
docker run -d -p 8000:8000 --env-file .env enterprise-ai-backend:latest
```

**Build Frontend:**
```bash
docker build -t enterprise-ai-frontend:latest ./frontend
docker run -d -p 3000:3000 enterprise-ai-frontend:latest
```

Both containers run as unprivileged, non-root users (`appuser` UID 10001 / `nextjs` UID 1001) for container security.

---

## 5. Database Migrations & Safety

Database migrations are managed via Alembic:

```bash
# Check for pending model diffs
alembic check

# Apply migrations to latest head
alembic upgrade head

# Rollback one migration (if needed)
alembic downgrade -1
```

### Production Migration Sequence:
1. Snapshot / backup PostgreSQL database (`pg_dump`).
2. Deploy new backend code.
3. Run `alembic upgrade head`.
4. Verify readiness via `GET /api/v1/ready`.
5. Run automated smoke tests.

---

## 6. Health & Readiness Probes

The backend provides dual health check endpoints configured for Docker, Kubernetes, and load balancers:

- **Liveness Probe**: `GET /api/v1/health`
  - Returns `200 OK` when the FastAPI application process is alive.
- **Readiness Probe**: `GET /api/v1/ready`
  - Returns `200 OK` when the database connection pool is active and operational.

---

## 7. Testing & Verification

Run the full pytest suite (Phases 1–14):

```bash
cd backend
pytest -v
```

### Smoke Test Suite
An end-to-end smoke test suite is included in `tests/test_smoke.py` validating registration, RBAC, document upload, RAG search, tool execution, HITL approval, workflow orchestration, evaluation, and tenant isolation:

```bash
pytest tests/test_smoke.py -v
```

---

## 8. CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on all pushes and pull requests to `main`:
1. **Backend Checks**: Installs dependencies, applies Alembic migrations, runs full pytest suite against real PostgreSQL and Redis service containers.
2. **Frontend Checks**: Validates TypeScript types and compiles Next.js production build (`npm run build`).
3. **Docker Build Checks**: Builds production Docker images for both backend and frontend.

---

## 9. Rollback & Disaster Recovery

- **Application Rollback**: Re-deploy the previous container image tag. Container configurations are stateless.
- **Database Rollback**: Revert specific migrations via `alembic downgrade <revision_id>` or restore from `pg_dump` snapshot.
- **Redis Outage**: If Redis becomes unreachable, the rate limiter automatically falls back to in-memory sliding-window operation, ensuring no service disruption.
- **LLM Outage**: The assistant catches provider timeouts and rate limits, categorizing them under `LLM_ERROR` in observability traces while failing gracefully.

---

## 10. License & Maintenance
Enterprise AI Assistant — Released under the MIT License.
