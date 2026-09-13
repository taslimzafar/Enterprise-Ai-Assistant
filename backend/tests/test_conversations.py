import pytest
import uuid
from httpx import AsyncClient
from app.core.config import settings
from app.db.models.document import Document, DocumentStatus
from app.db.models.document_chunk import DocumentChunk
import app.services.embeddings as emb_module


@pytest.fixture
async def auth_user_and_org(async_client: AsyncClient):
    """Register and login a test user, returning headers, user, and organization."""
    suffix = uuid.uuid4().hex[:6]
    email = f"chat_user_{suffix}@example.com"
    pwd = "ChatPassword123!"

    reg = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": pwd, "full_name": "Chat Test User"},
    )
    assert reg.status_code == 200

    login = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": email, "password": pwd},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    orgs = await async_client.get(f"{settings.API_V1_STR}/organizations/", headers=headers)
    assert orgs.status_code == 200
    org_id = orgs.json()[0]["id"]

    return {"headers": headers, "org_id": org_id, "email": email}


@pytest.fixture
async def second_tenant(async_client: AsyncClient):
    """Register a distinct user and organization for cross-tenant testing."""
    suffix = uuid.uuid4().hex[:6]
    email = f"second_chat_{suffix}@example.com"
    pwd = "SecondPassword123!"

    await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": pwd, "full_name": "Second Tenant User"},
    )
    login = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": email, "password": pwd},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    orgs = await async_client.get(f"{settings.API_V1_STR}/organizations/", headers=headers)
    org_id = orgs.json()[0]["id"]
    return {"headers": headers, "org_id": org_id, "email": email}


@pytest.mark.asyncio
async def test_conversation_crud(async_client: AsyncClient, auth_user_and_org: dict):
    headers = auth_user_and_org["headers"]
    org_id = auth_user_and_org["org_id"]

    # 1. Create conversation
    res = await async_client.post(
        f"{settings.API_V1_STR}/conversations?org_id={org_id}",
        json={"title": "Test Chat Conversation"},
        headers=headers,
    )
    assert res.status_code == 201
    conv = res.json()
    conv_id = conv["id"]
    assert conv["title"] == "Test Chat Conversation"
    assert conv["organization_id"] == org_id

    # 2. List conversations
    list_res = await async_client.get(
        f"{settings.API_V1_STR}/conversations?org_id={org_id}",
        headers=headers,
    )
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(c["id"] == conv_id for c in items)

    # 3. Retrieve conversation
    get_res = await async_client.get(
        f"{settings.API_V1_STR}/conversations/{conv_id}?org_id={org_id}",
        headers=headers,
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == conv_id

    # 4. Rename conversation
    patch_res = await async_client.patch(
        f"{settings.API_V1_STR}/conversations/{conv_id}?org_id={org_id}",
        json={"title": "Updated Chat Title"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["title"] == "Updated Chat Title"

    # 5. Delete conversation
    del_res = await async_client.delete(
        f"{settings.API_V1_STR}/conversations/{conv_id}?org_id={org_id}",
        headers=headers,
    )
    assert del_res.status_code == 204

    # Verify deleted
    get_del = await async_client.get(
        f"{settings.API_V1_STR}/conversations/{conv_id}?org_id={org_id}",
        headers=headers,
    )
    assert get_del.status_code == 404


@pytest.mark.asyncio
async def test_chat_stream_sse_flow_and_citations(
    async_client: AsyncClient,
    auth_user_and_org: dict,
):
    headers = auth_user_and_org["headers"]
    org_id = auth_user_and_org["org_id"]

    # Ingest a test document with embeddings into this organization
    import app.db.database as db_module
    import json
    embedding_provider = emb_module._embedding_provider_instance
    sample_text = "Our corporate refund policy allows full refunds within 30 days of purchase."
    vec = await embedding_provider.embed_text(sample_text)

    async with db_module.async_session_maker() as session:
        doc = Document(
            organization_id=org_id,
            filename="test_refund.txt",
            original_filename="refund_policy.txt",
            file_type="txt",
            file_size=len(sample_text),
            storage_path="/storage/test_refund.txt",
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
            content=sample_text,
            char_count=len(sample_text),
            embedding=vec,
        )
        session.add(chunk)
        await session.commit()

    # Create a conversation
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/conversations?org_id={org_id}",
        json={},
        headers=headers,
    )
    assert c_res.status_code == 201
    conv_id = c_res.json()["id"]

    # Stream query
    stream_res = await async_client.post(
        f"{settings.API_V1_STR}/conversations/{conv_id}/stream?org_id={org_id}",
        json={"message": "What is our corporate refund policy?"},
        headers=headers,
    )
    assert stream_res.status_code == 200
    assert "text/event-stream" in stream_res.headers["content-type"]

    body = stream_res.text
    assert "event: message_start" in body
    assert "event: citation" in body
    assert "event: token" in body
    assert "event: message_complete" in body

    # Reconstruct streamed text
    tokens = [
        json.loads(line[6:])["text"]
        for line in body.splitlines()
        if line.startswith("data: ") and '"text":' in line
    ]
    streamed_text = "".join(tokens)
    assert "refund" in streamed_text.lower()

    # Verify message persistence in DB
    msg_res = await async_client.get(
        f"{settings.API_V1_STR}/conversations/{conv_id}/messages?org_id={org_id}",
        headers=headers,
    )
    assert msg_res.status_code == 200
    msgs = msg_res.json()
    assert len(msgs) == 2  # user message and assistant message
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "What is our corporate refund policy?"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["status"] == "completed"
    assert "refund" in msgs[1]["content"].lower()


@pytest.mark.asyncio
async def test_chat_stream_no_answer_fallback(
    async_client: AsyncClient,
    auth_user_and_org: dict,
):
    import json
    headers = auth_user_and_org["headers"]
    org_id = auth_user_and_org["org_id"]

    # Create conversation
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/conversations?org_id={org_id}",
        json={"title": "Empty Chat"},
        headers=headers,
    )
    conv_id = c_res.json()["id"]

    # Query without any relevant documents
    stream_res = await async_client.post(
        f"{settings.API_V1_STR}/conversations/{conv_id}/stream?org_id={org_id}",
        json={"message": "What is the secret formula?"},
        headers=headers,
    )
    assert stream_res.status_code == 200
    body = stream_res.text
    assert "event: token" in body
    tokens = [
        json.loads(line[6:])["text"]
        for line in body.splitlines()
        if line.startswith("data: ") and '"text":' in line
    ]
    streamed_text = "".join(tokens)
    assert "couldn't find this information" in streamed_text.lower() or "could not find" in streamed_text.lower()


@pytest.mark.asyncio
async def test_cross_tenant_conversation_isolation(
    async_client: AsyncClient,
    auth_user_and_org: dict,
    second_tenant: dict,
):
    headers_1 = auth_user_and_org["headers"]
    org_1 = auth_user_and_org["org_id"]
    headers_2 = second_tenant["headers"]
    org_2 = second_tenant["org_id"]

    # Tenant 1 creates conversation in Org 1
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/conversations?org_id={org_1}",
        json={"title": "Org 1 Confidential Conversation"},
        headers=headers_1,
    )
    assert c_res.status_code == 201
    conv_1_id = c_res.json()["id"]

    # 1. Tenant 2 tries to access Org 1 directly -> 403 Forbidden
    cross_res = await async_client.get(
        f"{settings.API_V1_STR}/conversations/{conv_1_id}?org_id={org_1}",
        headers=headers_2,
    )
    assert cross_res.status_code == 403

    # 2. Tenant 2 tries to access Conv 1 claiming it is in Org 2 -> 404 Not Found
    spoof_res = await async_client.get(
        f"{settings.API_V1_STR}/conversations/{conv_1_id}?org_id={org_2}",
        headers=headers_2,
    )
    assert spoof_res.status_code == 404

    # 3. Tenant 2 tries to stream into Tenant 1's conversation with forged org_1 -> 403 Forbidden
    stream_spoof = await async_client.post(
        f"{settings.API_V1_STR}/conversations/{conv_1_id}/stream?org_id={org_1}",
        json={"message": "Hacking conversation..."},
        headers=headers_2,
    )
    assert stream_spoof.status_code == 403

    # 4. Unauthenticated streaming -> 401 Unauthorized
    unauth_stream = await async_client.post(
        f"{settings.API_V1_STR}/conversations/{conv_1_id}/stream?org_id={org_1}",
        json={"message": "No token query"},
    )
    assert unauth_stream.status_code == 401
