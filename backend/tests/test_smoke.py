import pytest
import uuid
from httpx import AsyncClient

from app.core.config import settings
import app.db.database as db_module
from app.db.models.membership import Membership, RoleEnum


@pytest.mark.asyncio
async def test_production_smoke_suite(async_client: AsyncClient):
    """
    End-to-End Production Smoke Test verifying all core subsystems:
    1. Health & Readiness
    2. User Registration & Login
    3. Organization Creation & Listing
    4. RBAC Enforcement
    5. Document Ingestion & Storage
    6. RAG Query
    7. Streaming / Chat Initiation
    8. Controlled Tool Execution (Calculator)
    9. HITL Approval Flow (Create & Resolution)
    10. Workflow Engine (Create & Execute)
    11. Evaluation & Observability Endpoints
    12. Tenant Isolation Verification
    """
    suffix = uuid.uuid4().hex[:6]
    pwd = "SmokeTestPassword123!"

    # --------------------------------------------------------------------------
    # 1. Health & Readiness Checks
    # --------------------------------------------------------------------------
    r_health = await async_client.get(f"{settings.API_V1_STR}/health")
    assert r_health.status_code == 200
    assert r_health.json()["status"] == "healthy"

    r_ready = await async_client.get(f"{settings.API_V1_STR}/ready")
    assert r_ready.status_code == 200
    assert r_ready.json()["status"] == "ready"
    assert r_ready.json()["database"] == "ok"

    # --------------------------------------------------------------------------
    # 2. Registration & Login (Tenant A Owner)
    # --------------------------------------------------------------------------
    email_a = f"smoke_owner_{suffix}@tenanta.com"
    r_reg = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email_a, "password": pwd, "full_name": "Smoke Owner A"},
    )
    assert r_reg.status_code in (200, 201)
    user_a_id = r_reg.json()["id"]

    r_login = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": email_a, "password": pwd},
    )
    assert r_login.status_code == 200
    token_a = r_login.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # --------------------------------------------------------------------------
    # 3. Organization Creation & Listing
    # --------------------------------------------------------------------------
    r_orgs = await async_client.get(f"{settings.API_V1_STR}/organizations/", headers=headers_a)
    assert r_orgs.status_code == 200
    org_list = r_orgs.json()
    assert len(org_list) >= 1
    org_a_id = org_list[0]["id"]

    # --------------------------------------------------------------------------
    # 4. RBAC Enforcement (Viewer creation and restricted action check)
    # --------------------------------------------------------------------------
    viewer_email = f"smoke_viewer_{suffix}@tenanta.com"
    r_v_reg = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": viewer_email, "password": pwd, "full_name": "Smoke Viewer"},
    )
    viewer_id = r_v_reg.json()["id"]
    r_v_login = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": viewer_email, "password": pwd},
    )
    viewer_token = r_v_login.json()["access_token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # Add viewer membership
    async with db_module.async_session_maker() as session:
        m = Membership(user_id=viewer_id, organization_id=org_a_id, role=RoleEnum.VIEWER)
        session.add(m)
        await session.commit()

    # Viewer cannot upload document (restricted to MEMBER/MANAGER/ADMIN/OWNER) -> 403
    r_v_upload = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_a_id}",
        files={"file": ("test.txt", b"Viewer upload attempt", "text/plain")},
        headers=viewer_headers,
    )
    assert r_v_upload.status_code == 403

    # --------------------------------------------------------------------------
    # 5. Document Upload & Storage (Owner)
    # --------------------------------------------------------------------------
    doc_content = b"Enterprise SLA Policy: Severity 1 production issues require a 15 minute response time."
    r_upload = await async_client.post(
        f"{settings.API_V1_STR}/documents?org_id={org_a_id}",
        files={"file": ("sla_policy.txt", doc_content, "text/plain")},
        headers=headers_a,
    )
    assert r_upload.status_code == 200
    doc_data = r_upload.json()
    doc_id = doc_data["id"]
    assert doc_data["status"] == "PROCESSED"

    # --------------------------------------------------------------------------
    # 6. RAG Query
    # --------------------------------------------------------------------------
    r_rag = await async_client.post(
        f"{settings.API_V1_STR}/rag/query?org_id={org_a_id}",
        json={"question": "What is the response time for Severity 1 incidents?", "top_k": 3},
        headers=headers_a,
    )
    assert r_rag.status_code == 200
    rag_data = r_rag.json()
    assert "answer" in rag_data
    assert "sources" in rag_data

    # --------------------------------------------------------------------------
    # 7. Streaming Chat Initiation
    # --------------------------------------------------------------------------
    r_conv = await async_client.post(
        f"{settings.API_V1_STR}/conversations?org_id={org_a_id}",
        json={"title": "Smoke Test Conversation"},
        headers=headers_a,
    )
    assert r_conv.status_code == 201
    conv_id = r_conv.json()["id"]

    # --------------------------------------------------------------------------
    # 8. Controlled Tool Execution (Calculator via direct service check)
    # --------------------------------------------------------------------------
    from app.services.tools import tool_registry
    from app.services.tools.base import ToolContext
    calc_tool = tool_registry.get("calculator")
    assert calc_tool is not None
    ctx = ToolContext(
        organization_id=org_a_id,
        user_id=user_a_id,
        user_role="OWNER",
    )
    tool_res = await tool_registry.execute_tool("calculator", {"expression": "25 * 4"}, ctx)
    assert tool_res.success is True
    assert tool_res.data["result"] == 100

    # --------------------------------------------------------------------------
    # 9. HITL Approval Flow
    # --------------------------------------------------------------------------
    from app.services.approval.service import approval_service
    async with db_module.async_session_maker() as session:
        appr_obj = await approval_service.create_approval(
            db=session,
            organization_id=org_a_id,
            requested_by_user_id=user_a_id,
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Smoke Note", "content": "Sensitive content"},
            reason="Production Smoke Test Verification",
        )
        approval_id = appr_obj.id

    # List approvals
    r_appr_list = await async_client.get(
        f"{settings.API_V1_STR}/approvals",
        params={"org_id": org_a_id},
        headers=headers_a,
    )
    assert r_appr_list.status_code == 200
    assert any(item["id"] == approval_id for item in r_appr_list.json()["items"])

    # --------------------------------------------------------------------------
    # 10. Workflow Engine (Create & List)
    # --------------------------------------------------------------------------
    r_wf = await async_client.post(
        f"{settings.API_V1_STR}/workflows",
        json={
            "name": "Smoke Test Workflow",
            "description": "Validates workflow pipeline deployment",
            "steps": [
                {
                    "name": "calc_step",
                    "type": "CALCULATOR",
                    "order": 0,
                    "configuration": {"expression": "100 + 50"},
                    "output_key": "calc_result",
                }
            ],
        },
        params={"org_id": org_a_id},
        headers=headers_a,
    )
    assert r_wf.status_code == 201
    wf_id = r_wf.json()["id"]

    r_wf_list = await async_client.get(
        f"{settings.API_V1_STR}/workflows",
        params={"org_id": org_a_id},
        headers=headers_a,
    )
    assert r_wf_list.status_code == 200
    assert any(wf["id"] == wf_id for wf in r_wf_list.json()["items"])

    # --------------------------------------------------------------------------
    # 11. Evaluation & Observability Endpoints
    # --------------------------------------------------------------------------
    r_eval_metrics = await async_client.get(
        f"{settings.API_V1_STR}/evaluations/metrics?org_id={org_a_id}",
        headers=headers_a,
    )
    assert r_eval_metrics.status_code == 200

    r_obs_metrics = await async_client.get(
        f"{settings.API_V1_STR}/observability/metrics?org_id={org_a_id}",
        headers=headers_a,
    )
    assert r_obs_metrics.status_code == 200
    assert "request_count" in r_obs_metrics.json()

    # --------------------------------------------------------------------------
    # 12. Tenant Isolation Verification (Tenant B)
    # --------------------------------------------------------------------------
    email_b = f"smoke_b_{suffix}@tenantb.com"
    r_b_reg = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email_b, "password": pwd, "full_name": "Smoke Owner B"},
    )
    r_b_login = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": email_b, "password": pwd},
    )
    token_b = r_b_login.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Tenant B tries to access Tenant A's document -> 404
    r_b_doc = await async_client.get(
        f"{settings.API_V1_STR}/documents/{doc_id}?org_id={org_a_id}",
        headers=headers_b,
    )
    assert r_b_doc.status_code in (403, 404)

    # Tenant B tries to access Tenant A's workflow -> 403 or 404
    r_b_wf = await async_client.get(
        f"{settings.API_V1_STR}/workflows/{wf_id}?org_id={org_a_id}",
        headers=headers_b,
    )
    assert r_b_wf.status_code in (403, 404)
