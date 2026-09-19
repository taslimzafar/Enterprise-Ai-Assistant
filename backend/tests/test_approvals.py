import pytest
import uuid
import json
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
import app.db.database as db_module
from app.db.models.approval import Approval, ApprovalStatus
from app.db.models.membership import Membership, RoleEnum
from app.db.models.user import User
from app.services.approval.service import approval_service
from app.services.approval.permissions import ApprovalPermissionChecker
from app.services.approval.exceptions import (
    ApprovalNotFoundError,
    CrossTenantAccessError,
    ApprovalPermissionDeniedError,
    SelfApprovalForbiddenError,
    InvalidStateTransitionError,
    ApprovalExpiredError,
)
from app.services.tools import tool_registry
from app.services.agent import agent_service


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
async def multi_role_tenant(async_client: AsyncClient):
    """
    Sets up Tenant A with:
    - Owner (requester or approver)
    - Admin
    - Manager
    - Member
    - Viewer
    And Tenant B with:
    - Separate Owner
    """
    suffix = uuid.uuid4().hex[:6]
    
    # 1. Tenant A Owner
    owner_email = f"owner_{suffix}@tenanta.com"
    pwd = "TestPassword123!"
    reg_owner = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": owner_email, "password": pwd, "full_name": "Tenant A Owner"},
    )
    assert reg_owner.status_code == 200
    owner_id = reg_owner.json()["id"]

    login_owner = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": owner_email, "password": pwd},
    )
    owner_token = login_owner.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    orgs_resp = await async_client.get(f"{settings.API_V1_STR}/organizations/", headers=owner_headers)
    org_id = orgs_resp.json()[0]["id"]

    # Helper to register and attach membership
    async def create_tenant_user(role_name: str, role_enum: RoleEnum):
        u_email = f"{role_name}_{suffix}@tenanta.com"
        reg = await async_client.post(
            f"{settings.API_V1_STR}/auth/register",
            json={"email": u_email, "password": pwd, "full_name": f"User {role_name}"},
        )
        u_id = reg.json()["id"]

        login = await async_client.post(
            f"{settings.API_V1_STR}/auth/login",
            data={"username": u_email, "password": pwd},
        )
        u_token = login.json()["access_token"]
        u_headers = {"Authorization": f"Bearer {u_token}"}

        # Add to Tenant A with specific role
        async with db_module.async_session_maker() as session:
            m = Membership(user_id=u_id, organization_id=org_id, role=role_enum)
            session.add(m)
            await session.commit()

        return {"id": u_id, "email": u_email, "headers": u_headers, "role": role_name}

    admin_user = await create_tenant_user("admin", RoleEnum.ADMIN)
    manager_user = await create_tenant_user("manager", RoleEnum.MANAGER)
    member_user = await create_tenant_user("member", RoleEnum.MEMBER)
    viewer_user = await create_tenant_user("viewer", RoleEnum.MEMBER)

    # 2. Tenant B (Cross-tenant)
    b_suffix = uuid.uuid4().hex[:6]
    b_email = f"owner_{b_suffix}@tenantb.com"
    reg_b = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": b_email, "password": pwd, "full_name": "Tenant B Owner"},
    )
    b_id = reg_b.json()["id"]
    login_b = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": b_email, "password": pwd},
    )
    b_token = login_b.json()["access_token"]
    b_headers = {"Authorization": f"Bearer {b_token}"}
    b_orgs = await async_client.get(f"{settings.API_V1_STR}/organizations/", headers=b_headers)
    b_org_id = b_orgs.json()[0]["id"]

    return {
        "org_id": org_id,
        "owner": {"id": owner_id, "email": owner_email, "headers": owner_headers, "role": "OWNER"},
        "admin": admin_user,
        "manager": manager_user,
        "member": member_user,
        "viewer": viewer_user,
        "tenant_b": {"org_id": b_org_id, "id": b_id, "headers": b_headers},
    }


# ---------------------------------------------------------------------------
# 30 REQUIRED TESTS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_01_create_approval(multi_role_tenant):
    """1. Create approval request record."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        approval = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Test 1", "content": "Body 1"},
            reason="Testing note creation",
            expires_in_hours=12,
        )
        assert approval.id is not None
        assert approval.organization_id == t["org_id"]
        assert approval.requested_by_user_id == t["member"]["id"]
        assert approval.tool_name == "create_demo_note"
        assert approval.action_arguments == {"title": "Test 1", "content": "Body 1"}
        assert approval.status == ApprovalStatus.PENDING
        assert approval.expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_02_list_approvals(multi_role_tenant, async_client: AsyncClient):
    """2. List approvals scoped by organization and status."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "List Test", "content": "Content"},
            reason="For listing test",
        )

    res = await async_client.get(
        f"{settings.API_V1_STR}/approvals?org_id={t['org_id']}&status=PENDING",
        headers=t["owner"]["headers"],
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 1
    assert any(item["reason"] == "For listing test" for item in data["items"])


@pytest.mark.asyncio
async def test_03_get_approval(multi_role_tenant, async_client: AsyncClient):
    """3. Get specific approval details."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Get Test", "content": "Get body"},
            reason="Get detail test",
        )

    res = await async_client.get(
        f"{settings.API_V1_STR}/approvals/{appr.id}?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == appr.id
    assert data["tool_name"] == "create_demo_note"
    assert data["status"] == "PENDING"


@pytest.mark.asyncio
async def test_04_approve_pending_approval(multi_role_tenant, async_client: AsyncClient):
    """4. Approve pending approval by authorized manager."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Approve Me", "content": "Body"},
            reason="Approve test",
        )

    res = await async_client.post(
        f"{settings.API_V1_STR}/approvals/{appr.id}/approve?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "APPROVED"
    assert data["approved_by_user_id"] == t["manager"]["id"]
    assert data["approved_at"] is not None


@pytest.mark.asyncio
async def test_05_reject_pending_approval(multi_role_tenant, async_client: AsyncClient):
    """5. Reject pending approval with reason."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Reject Me", "content": "Body"},
            reason="Reject test",
        )

    res = await async_client.post(
        f"{settings.API_V1_STR}/approvals/{appr.id}/reject?org_id={t['org_id']}",
        json={"rejection_reason": "Not compliant with policy."},
        headers=t["admin"]["headers"],
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "REJECTED"
    assert data["rejection_reason"] == "Not compliant with policy."


@pytest.mark.asyncio
async def test_06_cancel_pending_approval(multi_role_tenant, async_client: AsyncClient):
    """6. Cancel pending approval by the requester."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Cancel Me", "content": "Body"},
            reason="Cancel test",
        )

    res = await async_client.post(
        f"{settings.API_V1_STR}/approvals/{appr.id}/cancel?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert res.status_code == 200
    assert res.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_07_expiration(multi_role_tenant):
    """7. Stale approvals expire automatically."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        # Create approval with expired time in past
        appr = Approval(
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Expired Note"},
            reason="Testing expiration",
            status=ApprovalStatus.PENDING,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        session.add(appr)
        await session.commit()
        await session.refresh(appr)
        expired_id = appr.id

        # Run expiration batch
        expired_count = await approval_service.expire_stale_approvals(session)
        assert expired_count >= 1

        # Check approval status is now EXPIRED
        updated = await approval_service.get_approval(session, expired_id, t["org_id"])
        assert updated.status == ApprovalStatus.EXPIRED

        # Trying to approve expired approval raises ApprovalExpiredError or InvalidStateTransitionError
        with pytest.raises((ApprovalExpiredError, InvalidStateTransitionError)):
            await approval_service.approve(
                session, expired_id, t["org_id"], t["manager"]["id"], "MANAGER"
            )

        # Also test direct expiration when approving a pending request past its expiration
        appr_pending_expired = Approval(
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Pending Expired Note"},
            reason="Testing direct expiration on approve",
            status=ApprovalStatus.PENDING,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        session.add(appr_pending_expired)
        await session.commit()
        await session.refresh(appr_pending_expired)

        with pytest.raises(ApprovalExpiredError):
            await approval_service.approve(
                session, appr_pending_expired.id, t["org_id"], t["manager"]["id"], "MANAGER"
            )



@pytest.mark.asyncio
async def test_08_invalid_state_transition(multi_role_tenant):
    """8. Invalid state transitions are rejected."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "State Transition"},
            reason="State test",
        )
        appr_id = appr.id

        # Approve it first -> Terminal state APPROVED
        await approval_service.approve(session, appr_id, t["org_id"], t["manager"]["id"], "MANAGER")

        # Attempting APPROVED -> REJECTED must raise InvalidStateTransitionError
        with pytest.raises(InvalidStateTransitionError):
            await approval_service.reject(session, appr_id, t["org_id"], t["manager"]["id"], "MANAGER")

        # Attempting APPROVED -> CANCELLED must raise InvalidStateTransitionError
        with pytest.raises(InvalidStateTransitionError):
            await approval_service.cancel(session, appr_id, t["org_id"], t["member"]["id"], "MEMBER")


@pytest.mark.asyncio
async def test_09_unauthorized_approval(multi_role_tenant):
    """9. Non-member cannot approve action."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={},
            reason="Unauthorized test",
        )

        with pytest.raises(ApprovalPermissionDeniedError):
            await approval_service.approve(
                session, appr.id, t["org_id"], "random-non-member-id", "OUTSIDER"
            )


@pytest.mark.asyncio
async def test_10_cross_tenant_approval_access(multi_role_tenant, async_client: AsyncClient):
    """10. Cross-tenant user cannot view another tenant's approval."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={},
            reason="Tenant isolation test",
        )

    # Tenant B tries to access Tenant A's approval
    res = await async_client.get(
        f"{settings.API_V1_STR}/approvals/{appr.id}?org_id={t['tenant_b']['org_id']}",
        headers=t["tenant_b"]["headers"],
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_11_cross_tenant_approval_mutation(multi_role_tenant, async_client: AsyncClient):
    """11. Cross-tenant user cannot approve or reject another tenant's approval."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={},
            reason="Cross tenant mutation test",
        )

    res = await async_client.post(
        f"{settings.API_V1_STR}/approvals/{appr.id}/approve?org_id={t['tenant_b']['org_id']}",
        headers=t["tenant_b"]["headers"],
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_12_member_cannot_approve(multi_role_tenant, async_client: AsyncClient):
    """12. MEMBER role cannot approve actions."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["owner"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={},
            reason="Member test",
        )

    res = await async_client.post(
        f"{settings.API_V1_STR}/approvals/{appr.id}/approve?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_13_viewer_cannot_approve(multi_role_tenant, async_client: AsyncClient):
    """13. VIEWER role cannot approve actions."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["owner"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={},
            reason="Viewer test",
        )

    res = await async_client.post(
        f"{settings.API_V1_STR}/approvals/{appr.id}/approve?org_id={t['org_id']}",
        headers=t["viewer"]["headers"],
    )
    assert res.status_code == 403

    # Also directly verify permission checker denies VIEWER
    with pytest.raises(ApprovalPermissionDeniedError):
        ApprovalPermissionChecker.verify_approval_permission(
            approver_user_id="viewer-id",
            approver_role="VIEWER",
            requested_by_user_id="other-user",
        )



@pytest.mark.asyncio
async def test_14_admin_can_approve(multi_role_tenant, async_client: AsyncClient):
    """14. ADMIN role can approve actions."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={},
            reason="Admin approve test",
        )

    res = await async_client.post(
        f"{settings.API_V1_STR}/approvals/{appr.id}/approve?org_id={t['org_id']}",
        headers=t["admin"]["headers"],
    )
    assert res.status_code == 200
    assert res.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_15_manager_can_approve(multi_role_tenant, async_client: AsyncClient):
    """15. MANAGER role can approve actions."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={},
            reason="Manager approve test",
        )

    res = await async_client.post(
        f"{settings.API_V1_STR}/approvals/{appr.id}/approve?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )
    assert res.status_code == 200
    assert res.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_16_owner_can_approve(multi_role_tenant, async_client: AsyncClient):
    """16. OWNER role can approve actions."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={},
            reason="Owner approve test",
        )

    res = await async_client.post(
        f"{settings.API_V1_STR}/approvals/{appr.id}/approve?org_id={t['org_id']}",
        headers=t["owner"]["headers"],
    )
    assert res.status_code == 200
    assert res.json()["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_17_requester_cannot_self_approve(multi_role_tenant, async_client: AsyncClient):
    """17. Requester cannot self-approve their own sensitive action even if OWNER."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["owner"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={},
            reason="Self-approval violation test",
        )

    # Owner tries to approve own action
    res = await async_client.post(
        f"{settings.API_V1_STR}/approvals/{appr.id}/approve?org_id={t['org_id']}",
        headers=t["owner"]["headers"],
    )
    assert res.status_code == 403
    assert "Anti-self-approval policy violation" in res.json()["detail"]


@pytest.mark.asyncio
async def test_18_tool_requiring_approval_creates_approval(multi_role_tenant):
    """18. Tool declaring requires_approval=True pauses and creates approval record."""
    t = multi_role_tenant
    tool = tool_registry.get("create_demo_note")
    assert tool is not None
    assert tool.requires_approval is True

    result_state = await agent_service.run(
        organization_id=t["org_id"],
        user_id=t["member"]["id"],
        conversation_id="conv-demo-18",
        message="Please create demo note for Q3 goals",
        user_role="MEMBER",
    )

    assert result_state.get("approval_required") is True
    assert result_state.get("approval_status") == "PENDING"
    assert result_state.get("approval_id") is not None

    # Check approval in database
    async with db_module.async_session_maker() as session:
        appr = await approval_service.get_approval(session, result_state["approval_id"], t["org_id"])
        assert appr.status == ApprovalStatus.PENDING
        assert appr.tool_name == "create_demo_note"


@pytest.mark.asyncio
async def test_19_safe_tool_does_not_create_approval(multi_role_tenant):
    """19. Safe tools (calculator, knowledge_search) do NOT create approval requests."""
    t = multi_role_tenant
    tool = tool_registry.get("calculator")
    assert tool is not None
    assert tool.requires_approval is False

    result_state = await agent_service.run(
        organization_id=t["org_id"],
        user_id=t["member"]["id"],
        conversation_id="conv-calc-19",
        message="Please calculate 25 * 4",
        user_role="MEMBER",
    )

    assert result_state.get("approval_required") is False
    assert result_state.get("approval_id") is None
    tool_res = result_state.get("tool_result")
    assert tool_res == "100" or (isinstance(tool_res, dict) and tool_res.get("result") == 100)


@pytest.mark.asyncio
async def test_20_rejected_approval_prevents_execution(multi_role_tenant):
    """20. Rejected approval blocks tool execution."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Test Note", "content": "Demo note body"},
            reason="Testing rejection block",
        )
        await approval_service.reject(
            session, appr.id, t["org_id"], t["manager"]["id"], "MANAGER", "Rejected by policy"
        )
        rejected_id = appr.id

    # Run agent passing rejected approval ID
    result_state = await agent_service.run(
        organization_id=t["org_id"],
        user_id=t["member"]["id"],
        conversation_id="conv-demo-20",
        message="Please create demo note for Q3 goals",
        user_role="MEMBER",
        approval_id=rejected_id,
    )

    assert result_state.get("approval_status") == "REJECTED"
    assert "rejected" in result_state.get("tool_error", "").lower()
    assert result_state.get("tool_result") is None


@pytest.mark.asyncio
async def test_21_approved_approval_allows_execution(multi_role_tenant):
    """21. Approved approval allows tool execution."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Test Note", "content": "Demo note body"},
            reason="Testing approved execution",
        )
        await approval_service.approve(
            session, appr.id, t["org_id"], t["manager"]["id"], "MANAGER"
        )
        approved_id = appr.id

    # Run agent with approved approval ID
    result_state = await agent_service.run(
        organization_id=t["org_id"],
        user_id=t["member"]["id"],
        conversation_id="conv-demo-21",
        message="Please create demo note for Q3 goals",
        user_role="MEMBER",
        approval_id=approved_id,
    )

    assert result_state.get("approval_status") == "APPROVED"
    assert result_state.get("tool_error") is None
    assert result_state.get("tool_result") is not None
    assert "note_id" in result_state.get("tool_result", {})


@pytest.mark.asyncio
async def test_22_expired_approval_prevents_execution(multi_role_tenant):
    """22. Expired approval prevents tool execution."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = Approval(
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Test Note", "content": "Demo note body"},
            reason="Testing expired prevention",
            status=ApprovalStatus.EXPIRED,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        session.add(appr)
        await session.commit()
        await session.refresh(appr)
        expired_id = appr.id

    result_state = await agent_service.run(
        organization_id=t["org_id"],
        user_id=t["member"]["id"],
        conversation_id="conv-demo-22",
        message="Please create demo note for Q3 goals",
        user_role="MEMBER",
        approval_id=expired_id,
    )

    assert result_state.get("approval_status") == "EXPIRED"
    assert "expired" in result_state.get("tool_error", "").lower()
    assert result_state.get("tool_result") is None


@pytest.mark.asyncio
async def test_23_modified_arguments_rejected(multi_role_tenant):
    """23. Tamper protection: Modified tool arguments reject execution."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        # Approval created with specific title
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Original Approved Title", "content": "Original Content"},
            reason="Testing argument tampering",
        )
        await approval_service.approve(
            session, appr.id, t["org_id"], t["manager"]["id"], "MANAGER"
        )
        approved_id = appr.id

    # Test LLM provider generates {"title": "Test Note", "content": "Demo note body"}, which differs from "Original Approved Title"
    result_state = await agent_service.run(
        organization_id=t["org_id"],
        user_id=t["member"]["id"],
        conversation_id="conv-demo-23",
        message="Please create demo note for Q3 goals",
        user_role="MEMBER",
        approval_id=approved_id,
    )

    assert result_state.get("approval_status") == "REJECTED"
    assert "tampering" in result_state.get("tool_error", "").lower() or "mismatch" in result_state.get("tool_error", "").lower()
    assert result_state.get("tool_result") is None


@pytest.mark.asyncio
async def test_24_modified_tool_rejected(multi_role_tenant):
    """24. Tamper protection: Modified tool name rejects execution."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="different_tool_name",
            action_type="create_note",
            action_arguments={"title": "Test Note", "content": "Demo note body"},
            reason="Testing tool tampering",
        )
        await approval_service.approve(
            session, appr.id, t["org_id"], t["manager"]["id"], "MANAGER"
        )
        approved_id = appr.id

    result_state = await agent_service.run(
        organization_id=t["org_id"],
        user_id=t["member"]["id"],
        conversation_id="conv-demo-24",
        message="Please create demo note for Q3 goals",
        user_role="MEMBER",
        approval_id=approved_id,
    )

    assert result_state.get("approval_status") == "REJECTED"
    assert "mismatch" in result_state.get("tool_error", "").lower()
    assert result_state.get("tool_result") is None


@pytest.mark.asyncio
async def test_25_replay_protection(multi_role_tenant):
    """25. Replay protection: Expired or invalid terminal state transitions prevent replay."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Test Note", "content": "Demo note body"},
            reason="Testing replay protection",
        )
        await approval_service.reject(
            session, appr.id, t["org_id"], t["manager"]["id"], "MANAGER"
        )
        rejected_id = appr.id

        # Attacker cannot re-approve an already rejected approval
        with pytest.raises(InvalidStateTransitionError):
            await approval_service.approve(
                session, rejected_id, t["org_id"], t["manager"]["id"], "MANAGER"
            )


@pytest.mark.asyncio
async def test_26_duplicate_approval_protection(multi_role_tenant):
    """26. Duplicate approval protection: Once approved, cannot be approved again."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Test Note", "content": "Demo note body"},
            reason="Testing duplicate approval protection",
        )
        await approval_service.approve(
            session, appr.id, t["org_id"], t["manager"]["id"], "MANAGER"
        )

        with pytest.raises(InvalidStateTransitionError):
            await approval_service.approve(
                session, appr.id, t["org_id"], t["admin"]["id"], "ADMIN"
            )


@pytest.mark.asyncio
async def test_27_sse_approval_required(multi_role_tenant, async_client: AsyncClient):
    """27. SSE stream emits approval_required event for sensitive tool."""
    t = multi_role_tenant
    # Create conversation
    conv_res = await async_client.post(
        f"{settings.API_V1_STR}/conversations?org_id={t['org_id']}",
        json={"title": "SSE Approval Test"},
        headers=t["member"]["headers"],
    )
    assert conv_res.status_code in {200, 201}
    conv_id = conv_res.json()["id"]

    # Stream chat triggering sensitive tool
    response = await async_client.post(
        f"{settings.API_V1_STR}/conversations/{conv_id}/stream?org_id={t['org_id']}",
        json={"message": "Please create demo note for testing"},
        headers=t["member"]["headers"],
    )
    assert response.status_code == 200
    content = response.text

    assert "event: approval_required" in content
    assert "create_demo_note" in content


@pytest.mark.asyncio
async def test_28_sse_approval_approved(multi_role_tenant, async_client: AsyncClient):
    """28. SSE stream emits approval_approved event when resuming with approved ID."""
    t = multi_role_tenant
    conv_res = await async_client.post(
        f"{settings.API_V1_STR}/conversations?org_id={t['org_id']}",
        json={"title": "SSE Approved Resume Test"},
        headers=t["member"]["headers"],
    )
    assert conv_res.status_code in {200, 201}
    conv_id = conv_res.json()["id"]

    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Test Note", "content": "Demo note body"},
            reason="Resume approved stream test",
            conversation_id=conv_id,
        )
        await approval_service.approve(
            session, appr.id, t["org_id"], t["manager"]["id"], "MANAGER"
        )
        approved_id = appr.id

    # Resume stream with approved_id
    response = await async_client.post(
        f"{settings.API_V1_STR}/conversations/{conv_id}/stream?org_id={t['org_id']}",
        json={"message": "create demo note", "approval_id": approved_id},
        headers=t["member"]["headers"],
    )
    assert response.status_code == 200
    content = response.text

    assert "event: approval_approved" in content
    assert "event: tool_start" in content
    assert "event: tool_complete" in content


@pytest.mark.asyncio
async def test_29_sse_approval_rejected(multi_role_tenant, async_client: AsyncClient):
    """29. SSE stream emits approval_rejected event when resuming with rejected ID."""
    t = multi_role_tenant
    conv_res = await async_client.post(
        f"{settings.API_V1_STR}/conversations?org_id={t['org_id']}",
        json={"title": "SSE Rejected Resume Test"},
        headers=t["member"]["headers"],
    )
    assert conv_res.status_code in {200, 201}
    conv_id = conv_res.json()["id"]

    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Test Note", "content": "Demo note body"},
            reason="Resume rejected stream test",
            conversation_id=conv_id,
        )
        await approval_service.reject(
            session, appr.id, t["org_id"], t["manager"]["id"], "MANAGER", "Explicitly declined"
        )
        rejected_id = appr.id

    # Resume stream with rejected_id
    response = await async_client.post(
        f"{settings.API_V1_STR}/conversations/{conv_id}/stream?org_id={t['org_id']}",
        json={"message": "create demo note", "approval_id": rejected_id},
        headers=t["member"]["headers"],
    )
    assert response.status_code == 200
    content = response.text

    assert "event: approval_rejected" in content


@pytest.mark.asyncio
async def test_30_no_secret_leakage(multi_role_tenant, async_client: AsyncClient):
    """30. Approvals API and SSE events do not leak secrets or chain-of-thought."""
    t = multi_role_tenant
    async with db_module.async_session_maker() as session:
        appr = await approval_service.create_approval(
            db=session,
            organization_id=t["org_id"],
            requested_by_user_id=t["member"]["id"],
            tool_name="create_demo_note",
            action_type="create_note",
            action_arguments={"title": "Secret Check", "content": "Safe body"},
            reason="No leak verification",
        )
        appr_id = appr.id

    res = await async_client.get(
        f"{settings.API_V1_STR}/approvals/{appr_id}?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )
    assert res.status_code == 200
    payload_str = res.text

    forbidden_terms = [
        "jwt_secret",
        "openai_api_key",
        "gemini_api_key",
        "password",
        "chain_of_thought",
        "system_prompt",
    ]
    for term in forbidden_terms:
        assert term not in payload_str.lower()
