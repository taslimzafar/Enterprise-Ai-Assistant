import pytest
import uuid
from httpx import AsyncClient
from app.core.config import settings
from app.db.models.document import Document, DocumentStatus
from app.db.models.document_chunk import DocumentChunk
from app.db.models.conversation import Conversation
from app.db.models.membership import Membership, RoleEnum
import app.db.database as db_module
import app.services.embeddings as emb_module
from app.services.tools import (
    tool_registry,
    ToolRegistry,
    ToolContext,
    ToolResult,
    BaseTool,
    CalculatorTool,
    KnowledgeSearchTool,
    DatabaseQueryTool,
    ToolPermissionChecker,
    ToolPermissionError,
)
from app.services.tools.calculator import CalculatorInput
from app.services.tools.knowledge_search import KnowledgeSearchInput
from app.services.tools.database_query import DatabaseQueryInput
from app.services.agent import agent_service


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture
async def tools_tenant(async_client: AsyncClient):
    """Register and login a tenant user, returning auth headers and IDs."""
    suffix = uuid.uuid4().hex[:6]
    email = f"tools_user_{suffix}@example.com"
    pwd = "ToolsPassword123!"

    reg = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": pwd, "full_name": "Tools User"},
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


# ---------------------------------------------------------------------------
# 1. TOOL REGISTRY TESTS
# ---------------------------------------------------------------------------

def test_tool_registry_registration_and_lookup():
    """Verify registry stores, retrieves, and lists tools."""
    registry = ToolRegistry()
    assert registry.get("calculator") is not None
    assert registry.get("knowledge_search") is not None
    assert registry.get("database_query") is not None
    assert registry.get("non_existent_tool") is None

    # Role-based availability
    viewer_tools = [t.name for t in registry.get_available_tools("VIEWER")]
    member_tools = [t.name for t in registry.get_available_tools("MEMBER")]
    manager_tools = [t.name for t in registry.get_available_tools("MANAGER")]

    assert "calculator" in viewer_tools
    assert "knowledge_search" not in viewer_tools
    assert "database_query" not in viewer_tools

    assert "calculator" in member_tools
    assert "knowledge_search" in member_tools
    assert "database_query" not in member_tools

    assert "calculator" in manager_tools
    assert "knowledge_search" in manager_tools
    assert "database_query" in manager_tools


# ---------------------------------------------------------------------------
# 2. CALCULATOR TOOL TESTS & MALICIOUS CODE INJECTION
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculator_arithmetic_success():
    """Verify safe calculator performs arithmetic correctly."""
    calc = CalculatorTool()
    ctx = ToolContext(organization_id="org-1", user_id="user-1", user_role="MEMBER")

    # Basic operations
    res = await calc.execute(CalculatorInput(expression="25 * 4"), ctx)
    assert res.success is True
    assert res.data["result"] == 100

    res = await calc.execute(CalculatorInput(expression="100 / 4"), ctx)
    assert res.success is True
    assert res.data["result"] == 25

    res = await calc.execute(CalculatorInput(expression="(12 + 8) * 3 - 10"), ctx)
    assert res.success is True
    assert res.data["result"] == 50

    res = await calc.execute(CalculatorInput(expression="abs(-42)"), ctx)
    assert res.success is True
    assert res.data["result"] == 42


@pytest.mark.asyncio
async def test_calculator_zero_division_and_overflow():
    """Verify calculator gracefully handles division by zero and excessive exponents."""
    calc = CalculatorTool()
    ctx = ToolContext(organization_id="org-1", user_id="user-1", user_role="MEMBER")

    # Zero division
    res = await calc.execute(CalculatorInput(expression="50 / 0"), ctx)
    assert res.success is False
    assert "zero" in res.error.lower()

    # Large exponent memory bomb rejection
    res = await calc.execute(CalculatorInput(expression="99 ** 9999"), ctx)
    assert res.success is False
    assert "exponent too large" in res.error.lower()


@pytest.mark.asyncio
async def test_calculator_malicious_code_injection_rejection():
    """Verify AST whitelist rejects arbitrary Python execution and attribute access."""
    calc = CalculatorTool()
    ctx = ToolContext(organization_id="org-1", user_id="user-1", user_role="MEMBER")

    malicious_payloads = [
        "__import__('os').system('echo pwned')",
        "open('/etc/passwd').read()",
        "eval('2+2')",
        "exec('x = 1')",
        "().__class__.__bases__[0].__subclasses__()",
        "import sys; sys.exit()",
        "[x for x in range(100)]",
    ]

    for payload in malicious_payloads:
        res = await calc.execute(CalculatorInput(expression=payload), ctx)
        assert res.success is False, f"Payload should have been rejected: {payload}"
        assert res.error is not None


# ---------------------------------------------------------------------------
# 3. DATABASE QUERY TOOL TESTS & SECURITY
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_database_query_operations_and_tenant_isolation(tools_tenant: dict):
    """Verify read-only operations and strict tenant isolation."""
    org_id = tools_tenant["org_id"]
    user_id = tools_tenant["user_id"]

    db_tool = DatabaseQueryTool()
    ctx = ToolContext(organization_id=org_id, user_id=user_id, user_role="ADMIN")

    # Ingest document into org_id
    async with db_module.async_session_maker() as session:
        doc = Document(
            organization_id=org_id,
            filename="quarterly_report.pdf",
            original_filename="quarterly_report.pdf",
            file_type="pdf",
            file_size=1024,
            storage_path="/storage/quarterly_report.pdf",
            status=DocumentStatus.PROCESSED,
            chunk_count=2,
        )
        session.add(doc)
        await session.commit()

    # 1. Count documents
    res_count = await db_tool.execute(DatabaseQueryInput(operation="count_documents"), ctx)
    assert res_count.success is True
    assert res_count.data["result"]["total_documents"] >= 1

    # 2. List document metadata
    res_list = await db_tool.execute(DatabaseQueryInput(operation="list_document_metadata"), ctx)
    assert res_list.success is True
    assert len(res_list.data["result"]["documents"]) >= 1
    assert res_list.data["result"]["documents"][0]["filename"] == "quarterly_report.pdf"

    # 3. Organization statistics
    res_stats = await db_tool.execute(DatabaseQueryInput(operation="organization_statistics"), ctx)
    assert res_stats.success is True
    assert res_stats.data["result"]["total_documents"] >= 1

    # 4. Cross-tenant isolation check: Querying with a different org_id returns 0
    other_ctx = ToolContext(organization_id="other-isolated-org", user_id=user_id, user_role="ADMIN")
    other_res = await db_tool.execute(DatabaseQueryInput(operation="count_documents"), other_ctx)
    assert other_res.success is True
    assert other_res.data["result"]["total_documents"] == 0


@pytest.mark.asyncio
async def test_database_query_mutation_rejection():
    """Verify that mutation SQL attempts are strictly rejected."""
    db_tool = DatabaseQueryTool()
    ctx = ToolContext(organization_id="org-1", user_id="user-1", user_role="ADMIN")

    # Raw SQL attempt
    res = await db_tool.execute(
        DatabaseQueryInput(operation="count_documents", raw_sql="DROP TABLE documents;"),
        ctx,
    )
    assert res.success is False
    assert "forbidden" in res.error.lower()


# ---------------------------------------------------------------------------
# 4. KNOWLEDGE SEARCH TOOL TESTS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_knowledge_search_tool_execution(tools_tenant: dict):
    """Verify knowledge_search wraps hybrid search and preserves citations."""
    org_id = tools_tenant["org_id"]
    user_id = tools_tenant["user_id"]

    embedding_provider = emb_module._embedding_provider_instance
    doc_text = "Standard annual leave entitlement is 25 working days per calendar year."
    vec = await embedding_provider.embed_text(doc_text)

    async with db_module.async_session_maker() as session:
        doc = Document(
            organization_id=org_id,
            filename="leave_policy.txt",
            original_filename="leave_policy.txt",
            file_type="txt",
            file_size=len(doc_text),
            storage_path="/storage/leave_policy.txt",
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

    ks_tool = KnowledgeSearchTool()
    ctx = ToolContext(organization_id=org_id, user_id=user_id, user_role="MEMBER")

    res = await ks_tool.execute(KnowledgeSearchInput(query="annual leave entitlement"), ctx)
    assert res.success is True
    assert res.data["chunks_found"] >= 1
    assert len(res.data["sources"]) >= 1
    assert "leave_policy.txt" in res.data["sources"][0]["filename"]
    assert len(res.data["chunks"]) >= 1
    assert "document_id" in res.data["chunks"][0]
    assert "content_snippet" in res.data["chunks"][0]


# ---------------------------------------------------------------------------
# 5. PERMISSIONS & RBAC TESTS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tool_permissions_enforcement():
    """Verify tool execution respects role hierarchy and permissions."""
    # VIEWER trying to execute database_query
    res_viewer = await tool_registry.execute_tool(
        tool_name="database_query",
        arguments={"operation": "count_documents"},
        context=ToolContext(organization_id="org-1", user_id="u1", user_role="VIEWER"),
    )
    assert res_viewer.success is False
    assert "not authorized" in res_viewer.error.lower()

    # MEMBER trying to execute database_query
    res_member = await tool_registry.execute_tool(
        tool_name="database_query",
        arguments={"operation": "count_documents"},
        context=ToolContext(organization_id="org-1", user_id="u1", user_role="MEMBER"),
    )
    assert res_member.success is False
    assert "not authorized" in res_member.error.lower()

    # MANAGER executing database_query
    res_manager = await tool_registry.execute_tool(
        tool_name="database_query",
        arguments={"operation": "count_documents"},
        context=ToolContext(organization_id="org-1", user_id="u1", user_role="MANAGER"),
    )
    assert res_manager.success is True

    # Unknown tool rejection
    res_unknown = await tool_registry.execute_tool(
        tool_name="hacker_exploit_tool",
        arguments={},
        context=ToolContext(organization_id="org-1", user_id="u1", user_role="OWNER"),
    )
    assert res_unknown.success is False
    assert "unregistered tool" in res_unknown.error.lower()


# ---------------------------------------------------------------------------
# 6. AGENT INTEGRATION & STREAMING TESTS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_tool_calling_workflow(tools_tenant: dict):
    """Verify agent invokes calculator tool and synthesizes answer."""
    org_id = tools_tenant["org_id"]
    user_id = tools_tenant["user_id"]

    final_state = await agent_service.run(
        organization_id=org_id,
        user_id=user_id,
        conversation_id="conv-tools-1",
        message="Calculate 25 * 4",
        user_role="MEMBER",
    )

    assert final_state["status"] == "completed"
    assert len(final_state.get("tool_history", [])) >= 1
    assert final_state["tool_history"][0]["tool"] == "calculator"
    assert final_state["tool_history"][0]["success"] is True
    assert "100" in final_state["final_answer"]


@pytest.mark.asyncio
async def test_agent_streaming_tool_events(tools_tenant: dict):
    """Verify stream_chat emits tool_start and tool_complete SSE events."""
    org_id = tools_tenant["org_id"]
    user_id = tools_tenant["user_id"]

    events = []
    async for item in agent_service.stream_chat(
        organization_id=org_id,
        user_id=user_id,
        conversation_id="conv-tools-stream",
        message="Calculate 25 * 4",
        user_role="MEMBER",
    ):
        events.append(item.get("event"))

    assert "agent_start" in events
    assert "tool_start" in events
    assert "tool_complete" in events
    assert "generation_start" in events
    assert "token" in events
    assert "agent_complete" in events
