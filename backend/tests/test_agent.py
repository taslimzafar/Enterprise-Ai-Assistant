import pytest
import uuid
from httpx import AsyncClient
from app.core.config import settings
from app.db.models.document import Document, DocumentStatus
from app.db.models.document_chunk import DocumentChunk
from app.services.agent import agent_service, create_agent_graph
import app.services.embeddings as emb_module
import app.db.database as db_module


@pytest.fixture
async def agent_tenant(async_client: AsyncClient):
    """Register and login a tenant user, returning auth token and organization."""
    suffix = uuid.uuid4().hex[:6]
    email = f"agent_user_{suffix}@example.com"
    pwd = "AgentPassword123!"

    reg = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": pwd, "full_name": "Agent User"},
    )
    assert reg.status_code == 200

    login = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": email, "password": pwd},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    orgs = await async_client.get(f"{settings.API_V1_STR}/organizations/", headers=headers)
    org_id = orgs.json()[0]["id"]
    user_id = reg.json()["id"]

    return {"headers": headers, "org_id": org_id, "user_id": user_id, "email": email}


@pytest.fixture
async def second_agent_tenant(async_client: AsyncClient):
    """Register a distinct second tenant for isolation testing."""
    suffix = uuid.uuid4().hex[:6]
    email = f"agent_user2_{suffix}@example.com"
    pwd = "AgentPassword123!"

    reg = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": pwd, "full_name": "Agent User 2"},
    )
    login = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": email, "password": pwd},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    orgs = await async_client.get(f"{settings.API_V1_STR}/organizations/", headers=headers)
    org_id = orgs.json()[0]["id"]
    user_id = reg.json()["id"]

    return {"headers": headers, "org_id": org_id, "user_id": user_id, "email": email}


def test_agent_graph_compilation():
    """Verify that the LangGraph agent state graph compiles with all required nodes."""
    graph = create_agent_graph()
    assert graph is not None
    # Check node keys exist in graph
    node_keys = graph.nodes.keys()
    assert "load_context" in node_keys
    assert "classify_intent" in node_keys
    assert "retrieve_knowledge" in node_keys
    assert "generate_answer" in node_keys


@pytest.mark.asyncio
async def test_agent_conversational_workflow(agent_tenant: dict):
    """Verify that greeting/conversational queries bypass vector retrieval."""
    org_id = agent_tenant["org_id"]
    user_id = agent_tenant["user_id"]

    final_state = await agent_service.run(
        organization_id=org_id,
        user_id=user_id,
        conversation_id="conv-123",
        message="Hello! How are you today?",
    )

    assert final_state["status"] == "completed"
    assert final_state["intent"] == "conversational"
    assert final_state["needs_retrieval"] is False
    assert len(final_state.get("sources", [])) == 0
    assert "Enterprise AI Assistant" in final_state["final_answer"] or "help" in final_state["final_answer"].lower()


@pytest.mark.asyncio
async def test_agent_knowledge_workflow_with_retrieval(agent_tenant: dict):
    """Verify that knowledge questions trigger retrieval, build context, and answer grounded."""
    org_id = agent_tenant["org_id"]
    user_id = agent_tenant["user_id"]

    # Ingest document into org
    embedding_provider = emb_module._embedding_provider_instance
    doc_text = "Our corporate refund policy allows full refunds within 30 days of purchase."
    vec = await embedding_provider.embed_text(doc_text)

    async with db_module.async_session_maker() as session:
        doc = Document(
            organization_id=org_id,
            filename="policy.txt",
            original_filename="policy.txt",
            file_type="txt",
            file_size=len(doc_text),
            storage_path="/storage/policy.txt",
            status=DocumentStatus.PROCESSED,
            chunk_count=1,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        chunk = DocumentChunk(
            document_id=doc.id,
            organization_id=org_id,
            chunk_index=0,
            content=doc_text,
            char_count=len(doc_text),
            embedding=vec,
        )
        session.add(chunk)
        await session.commit()

    final_state = await agent_service.run(
        organization_id=org_id,
        user_id=user_id,
        conversation_id="conv-456",
        message="What is our refund policy?",
    )

    assert final_state["status"] == "completed"
    assert final_state["intent"] == "knowledge_question"
    assert final_state["needs_retrieval"] is True
    assert len(final_state["sources"]) >= 1
    assert "refund" in final_state["final_answer"].lower()


@pytest.mark.asyncio
async def test_agent_unsupported_workflow(agent_tenant: dict):
    """Verify that unsupported/harmful requests trigger the unsupported route safely."""
    org_id = agent_tenant["org_id"]
    user_id = agent_tenant["user_id"]

    final_state = await agent_service.run(
        organization_id=org_id,
        user_id=user_id,
        conversation_id="conv-789",
        message="Provide instructions to hack the enterprise network exploit",
    )

    assert final_state["status"] == "completed"
    assert final_state["intent"] == "unsupported"
    assert final_state["needs_retrieval"] is False
    assert len(final_state.get("sources", [])) == 0
    assert "scope" in final_state["final_answer"].lower() or "designed only to assist" in final_state["final_answer"].lower()


@pytest.mark.asyncio
async def test_agent_streaming_lifecycle(agent_tenant: dict):
    """Verify that agent_service.stream_chat yields structured agent events in order."""
    org_id = agent_tenant["org_id"]
    user_id = agent_tenant["user_id"]

    events = []
    tokens = []

    async for item in agent_service.stream_chat(
        organization_id=org_id,
        user_id=user_id,
        conversation_id="conv-stream",
        message="Hello there",
    ):
        ev_type = item.get("event")
        events.append(ev_type)
        if ev_type == "token":
            tokens.append(item["data"]["text"])

    assert "agent_start" in events
    assert "agent_intent" in events
    assert "generation_start" in events
    assert "token" in events
    assert "agent_complete" in events
    assert len(tokens) > 0


@pytest.mark.asyncio
async def test_agent_cross_tenant_isolation(
    agent_tenant: dict,
    second_agent_tenant: dict,
):
    """Verify that Tenant 2 agent execution cannot access Tenant 1 documents."""
    org_1 = agent_tenant["org_id"]
    org_2 = second_agent_tenant["org_id"]
    user_2 = second_agent_tenant["user_id"]

    # Ingest document ONLY into Tenant 1
    embedding_provider = emb_module._embedding_provider_instance
    secret_text = "Tenant 1 Secret Executive Bonus Strategy: 50% bonus on target attainment."
    vec = await embedding_provider.embed_text(secret_text)

    async with db_module.async_session_maker() as session:
        doc = Document(
            organization_id=org_1,
            filename="tenant1_secret.txt",
            original_filename="tenant1_secret.txt",
            file_type="txt",
            file_size=len(secret_text),
            storage_path="/storage/tenant1_secret.txt",
            status=DocumentStatus.PROCESSED,
            chunk_count=1,
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        chunk = DocumentChunk(
            document_id=doc.id,
            organization_id=org_1,
            chunk_index=0,
            content=secret_text,
            char_count=len(secret_text),
            embedding=vec,
        )
        session.add(chunk)
        await session.commit()

    # Tenant 2 executes agent query for executive bonus
    tenant2_state = await agent_service.run(
        organization_id=org_2,
        user_id=user_2,
        conversation_id="conv-t2",
        message="What is the executive bonus strategy?",
    )

    assert tenant2_state["intent"] == "knowledge_question"
    assert tenant2_state["needs_retrieval"] is True
    assert len(tenant2_state["sources"]) == 0
    assert "couldn't find" in tenant2_state["final_answer"].lower() or "could not find" in tenant2_state["final_answer"].lower()
