import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import select, text
from app.core.config import settings
from app.db.models import Document, DocumentChunk
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.gemini import GeminiEmbeddingProvider
from app.services.embeddings.openai import OpenAIEmbeddingProvider
from app.services.retrieval import RetrievalService, ContextBuilder, RetrievalResult
from app.services.rag import RAGService, NO_ANSWER_FOUND


async def _register_and_login(async_client: AsyncClient, email: str = None, password: str = "Password123!"):
    """Helper to create user and get JWT access token."""
    email = email or f"raguser_{uuid.uuid4().hex[:8]}@example.com"
    reg = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": password, "full_name": "RAG Test User"},
    )
    assert reg.status_code == 200

    login = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": email, "password": password},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    orgs = await async_client.get(
        f"{settings.API_V1_STR}/organizations/",
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = orgs.json()[0]["id"]
    return token, org_id, email


# =====================================================================
# 1. Embedding Provider & Storage Tests
# =====================================================================

@pytest.mark.asyncio
async def test_embedding_provider_validation():
    """Verify provider initialization validates API keys correctly."""
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not set"):
        GeminiEmbeddingProvider(api_key="")

    with pytest.raises(ValueError, match="OPENAI_API_KEY is not set"):
        OpenAIEmbeddingProvider(api_key="")


@pytest.mark.asyncio
async def test_embedding_generation_and_storage(async_client: AsyncClient):
    """Verify document upload generates embeddings and stores them in PostgreSQL document_chunks."""
    token, org_id, _ = await _register_and_login(async_client)

    doc_content = b"Enterprise Security Protocol: All employee devices must have whole disk encryption enabled."
    upload_res = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("security_policy.txt", doc_content, "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert upload_res.status_code == 200
    doc_data = upload_res.json()
    assert doc_data["status"] == "PROCESSED"
    assert doc_data["chunk_count"] >= 1

    # Verify directly in PostgreSQL that the embedding vector is populated
    from tests.conftest import test_async_session_maker
    async with test_async_session_maker() as session:
        result = await session.execute(
            select(DocumentChunk).filter(DocumentChunk.document_id == doc_data["id"])
        )
        chunks = result.scalars().all()
        assert len(chunks) >= 1
        for c in chunks:
            assert c.embedding is not None
            # Verify 768 dimensions
            assert len(c.embedding) == 768


# =====================================================================
# 2. Retrieval & Hybrid Search Tests
# =====================================================================

@pytest.mark.asyncio
async def test_vector_and_keyword_retrieval(async_client: AsyncClient):
    """Test pgvector similarity search and PostgreSQL full-text search."""
    token, org_id, _ = await _register_and_login(async_client)

    doc_content = (
        b"Company Vacation Policy: Full-time employees accrue 20 days of paid vacation annually. "
        b"Carryover is limited to 5 unused vacation days into the following calendar year."
    )
    await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("vacation_policy.txt", doc_content, "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )

    from tests.conftest import test_async_session_maker
    retriever = RetrievalService()
    from app.services.embeddings import get_embedding_provider
    embedder = get_embedding_provider()

    async with test_async_session_maker() as session:
        # 1. Vector Search
        q_vec = await embedder.embed_text("How many vacation days can employees accrue?")
        vec_hits = await retriever.vector_search(q_vec, org_id, top_k=3, db=session)
        assert len(vec_hits) >= 1
        assert "vacation" in vec_hits[0].content.lower()

        # 2. Keyword Search
        kw_hits = await retriever.keyword_search("vacation carryover", org_id, top_k=3, db=session)
        assert len(kw_hits) >= 1
        assert "carryover" in kw_hits[0].content.lower()

        # 3. Hybrid Search
        hybrid_hits = await retriever.hybrid_search("vacation days", org_id, top_k=3, db=session)
        assert len(hybrid_hits) >= 1
        assert hybrid_hits[0].similarity_score > 0.0


# =====================================================================
# 3. Context Builder & Prompt Tests
# =====================================================================

def test_context_builder():
    """Verify ContextBuilder formats metadata and enforces character budget."""
    builder = ContextBuilder(max_chars=200)
    mock_chunks = [
        RetrievalResult(
            document_id="doc-1",
            chunk_id="chunk-1",
            content="First chunk content of information.",
            similarity_score=0.9,
            filename="doc1.pdf",
            page_number=2,
            chunk_index=0,
        ),
        RetrievalResult(
            document_id="doc-2",
            chunk_id="chunk-2",
            content="Second chunk content with additional information.",
            similarity_score=0.8,
            filename="doc2.docx",
            page_number=None,
            chunk_index=1,
        ),
    ]

    context_str, sources = builder.build_context(mock_chunks)
    assert "[Document: doc1.pdf, Page 2" in context_str
    assert len(sources) >= 1
    assert sources[0]["document_id"] == "doc-1"
    assert sources[0]["filename"] == "doc1.pdf"
    assert sources[0]["page"] == 2


# =====================================================================
# 4. End-to-End RAG Query & Citation API Tests
# =====================================================================

@pytest.mark.asyncio
async def test_rag_query_endpoint(async_client: AsyncClient):
    """Test POST /api/v1/rag/query returns a grounded response with citations."""
    token, org_id, _ = await _register_and_login(async_client)

    # Ingest document
    policy_doc = b"Customer Refund Policy: Customers can request a full refund within 30 days of purchase."
    await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("refund_policy.txt", policy_doc, "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Query RAG endpoint
    rag_res = await async_client.post(
        f"{settings.API_V1_STR}/rag/query?org_id={org_id}",
        json={"question": "What is the customer refund policy?", "top_k": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rag_res.status_code == 200
    data = rag_res.json()
    assert "refund" in data["answer"].lower()
    assert len(data["sources"]) >= 1
    assert data["sources"][0]["filename"] == "refund_policy.txt"
    assert data["sources"][0]["score"] > 0.0


@pytest.mark.asyncio
async def test_rag_no_answer_behavior(async_client: AsyncClient):
    """Test RAG returns controlled 'no answer found' message when no matching content exists."""
    token, org_id, _ = await _register_and_login(async_client)

    # Ingest document on a specific topic
    await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_id}",
        files={"file": ("office_hours.txt", b"Office hours are 9 AM to 5 PM Monday to Friday.", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Ask completely unrelated query with empty overlap
    rag_res = await async_client.post(
        f"{settings.API_V1_STR}/rag/query?org_id={org_id}",
        json={"question": "What is the secret nuclear submarine blueprint?", "top_k": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rag_res.status_code == 200
    data = rag_res.json()
    assert NO_ANSWER_FOUND in data["answer"] or "couldn't find" in data["answer"].lower()


# =====================================================================
# 5. Strict Cross-Tenant Isolation Tests (CRITICAL)
# =====================================================================

@pytest.mark.asyncio
async def test_cross_tenant_rag_isolation(async_client: AsyncClient):
    """Verify Organization A cannot retrieve or view Organization B's documents or answers."""
    # Tenant A
    token_a, org_a, _ = await _register_and_login(async_client)
    # Tenant B
    token_b, org_b, _ = await _register_and_login(async_client)

    # Upload secret document to Org B only
    secret_doc = b"Project Titan Confidential: The codename for our unannounced acquisition is Project Titan."
    await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_b}",
        files={"file": ("project_titan.txt", secret_doc, "text/plain")},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    # 1. Tenant A asks about Project Titan in Org A -> Must NOT find Tenant B's data
    res_a = await async_client.post(
        f"{settings.API_V1_STR}/rag/query?org_id={org_a}",
        json={"question": "What is Project Titan?"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_a.status_code == 200
    data_a = res_a.json()
    # Must NOT return Project Titan content
    assert "project titan" not in data_a["answer"].lower() or "couldn't find" in data_a["answer"].lower()
    # Sources must be completely empty
    assert len(data_a["sources"]) == 0

    # 2. Tenant A attempts to pass org_id=org_b directly -> Forbidden (403)
    res_tamper = await async_client.post(
        f"{settings.API_V1_STR}/rag/query?org_id={org_b}",
        json={"question": "What is Project Titan?"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_tamper.status_code == 403
    assert "Not a member of this organization" in res_tamper.json()["detail"]


# =====================================================================
# 6. Authorization and Validation Error Tests
# =====================================================================

@pytest.mark.asyncio
async def test_rag_unauthorized_and_invalid_queries(async_client: AsyncClient):
    """Test unauthenticated requests (401) and invalid inputs (400/422)."""
    token, org_id, _ = await _register_and_login(async_client)

    # 1. Unauthenticated request -> 401
    res_unauth = await async_client.post(
        f"{settings.API_V1_STR}/rag/query?org_id={org_id}",
        json={"question": "Any question?"},
    )
    assert res_unauth.status_code == 401

    # 2. Empty question -> 422 or 400
    res_empty = await async_client.post(
        f"{settings.API_V1_STR}/rag/query?org_id={org_id}",
        json={"question": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_empty.status_code in (400, 422)
