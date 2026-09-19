import pytest
import uuid
import json
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import settings
import app.db.database as db_module
from app.db.models.workflow import (
    Workflow,
    WorkflowStep,
    WorkflowExecution,
    WorkflowStepExecution,
    WorkflowStatus,
    ExecutionStatus,
    StepExecutionStatus,
    StepType,
)
from app.db.models.approval import Approval, ApprovalStatus
from app.services.approval.service import approval_service
from app.services.workflow.service import workflow_service
from app.services.workflow.engine import WorkflowEngine
from app.services.workflow.conditions import SafeConditionEvaluator
from app.services.workflow.schemas import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowStepCreate,
)
from app.db.models.membership import Membership, RoleEnum
from app.services.workflow.exceptions import (
    WorkflowNotFoundError,
    WorkflowExecutionNotFoundError,
    WorkflowValidationError,
    WorkflowStateError,
    InvalidStateTransitionError,
    InvalidConditionError,
)


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
async def wf_tenant(async_client: AsyncClient):
    """Setup Tenant A with Owner, Manager, Member, and Tenant B with separate Owner."""
    suffix = uuid.uuid4().hex[:6]
    pwd = "TestPassword123!"

    # 1. Tenant A Owner
    owner_email = f"wf_owner_{suffix}@tenanta.com"
    r_owner = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": owner_email, "password": pwd, "full_name": "WF Owner"},
    )
    owner_id = r_owner.json()["id"]
    l_owner = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": owner_email, "password": pwd},
    )
    owner_token = l_owner.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    orgs_resp = await async_client.get(f"{settings.API_V1_STR}/organizations/", headers=owner_headers)
    org_id = orgs_resp.json()[0]["id"]

    # Helper to register and attach membership
    async def create_tenant_user(role_name: str, role_enum: RoleEnum):
        u_email = f"{role_name}_{suffix}@tenanta.com"
        reg = await async_client.post(
            f"{settings.API_V1_STR}/auth/register",
            json={"email": u_email, "password": pwd, "full_name": f"WF {role_name}"},
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

    manager_user = await create_tenant_user("manager", RoleEnum.MANAGER)
    member_user = await create_tenant_user("member", RoleEnum.MEMBER)

    # 2. Tenant B
    b_suffix = uuid.uuid4().hex[:6]
    b_email = f"wf_b_{b_suffix}@tenantb.com"
    r_b = await async_client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": b_email, "password": pwd, "full_name": "Tenant B User"},
    )
    b_id = r_b.json()["id"]
    l_b = await async_client.post(
        f"{settings.API_V1_STR}/auth/login",
        data={"username": b_email, "password": pwd},
    )
    b_token = l_b.json()["access_token"]
    b_headers = {"Authorization": f"Bearer {b_token}"}
    b_orgs = await async_client.get(f"{settings.API_V1_STR}/organizations/", headers=b_headers)
    b_org_id = b_orgs.json()[0]["id"]

    return {
        "org_id": org_id,
        "owner": {"id": owner_id, "email": owner_email, "headers": owner_headers, "role": "OWNER"},
        "manager": manager_user,
        "member": member_user,
        "tenant_b": {"org_id": b_org_id, "id": b_id, "headers": b_headers},
    }


# ---------------------------------------------------------------------------
# 33 REQUIRED TESTS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_01_create_workflow(wf_tenant, async_client: AsyncClient):
    """1. Create workflow in DRAFT status with valid steps."""
    t = wf_tenant
    payload = {
        "name": "Metrics Analysis Workflow",
        "description": "Calculates KPI scores and generates summary",
        "steps": [
            {
                "name": "Calculate Base KPI",
                "type": "CALCULATOR",
                "order": 0,
                "configuration": {"expression": "50 * 2"},
                "input_mapping": {},
                "output_key": "kpi_score",
                "timeout_seconds": 20,
                "retry_count": 1,
                "requires_approval": False,
            },
            {
                "name": "Generate Summary",
                "type": "LLM_GENERATION",
                "order": 1,
                "configuration": {"prompt": "Score is {kpi_score}"},
                "input_mapping": {},
                "output_key": "kpi_summary",
                "timeout_seconds": 30,
                "retry_count": 0,
                "requires_approval": False,
            }
        ]
    }

    res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json=payload,
        headers=t["manager"]["headers"],
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Metrics Analysis Workflow"
    assert data["status"] == "DRAFT"
    assert data["version"] == 1
    assert len(data["steps"]) == 2
    assert data["steps"][0]["output_key"] == "kpi_score"


@pytest.mark.asyncio
async def test_02_list_workflows(wf_tenant, async_client: AsyncClient):
    """2. List workflows for organization."""
    t = wf_tenant
    res = await async_client.get(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_03_get_workflow(wf_tenant, async_client: AsyncClient):
    """3. Get workflow by ID."""
    t = wf_tenant
    # List to get existing ID
    list_res = await async_client.get(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    wf_id = list_res.json()["items"][0]["id"]

    res = await async_client.get(
        f"{settings.API_V1_STR}/workflows/{wf_id}?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == wf_id
    assert len(data["steps"]) >= 1


@pytest.mark.asyncio
async def test_04_update_workflow(wf_tenant, async_client: AsyncClient):
    """4. Update workflow increments version."""
    t = wf_tenant
    # Create draft
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={
            "name": "Pre-Update Workflow",
            "description": "Initial",
            "steps": [{"name": "Step A", "type": "ORGANIZATION_STATS", "output_key": "out_a"}]
        },
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]

    u_res = await async_client.patch(
        f"{settings.API_V1_STR}/workflows/{wf_id}?org_id={t['org_id']}",
        json={"name": "Post-Update Workflow", "description": "Updated"},
        headers=t["manager"]["headers"],
    )
    assert u_res.status_code == 200
    assert u_res.json()["name"] == "Post-Update Workflow"


@pytest.mark.asyncio
async def test_05_activate_workflow(wf_tenant, async_client: AsyncClient):
    """5. Activate workflow moves status to ACTIVE."""
    t = wf_tenant
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={
            "name": "Activation Target",
            "steps": [{"name": "Step 1", "type": "CALCULATOR", "configuration": {"expression": "10+5"}, "output_key": "out_1"}]
        },
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]

    act_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows/{wf_id}/activate?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )
    assert act_res.status_code == 200
    assert act_res.json()["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_06_archive_workflow(wf_tenant, async_client: AsyncClient):
    """6. Archive workflow moves status to ARCHIVED."""
    t = wf_tenant
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={
            "name": "Archive Target",
            "steps": [{"name": "Step 1", "type": "CALCULATOR", "configuration": {"expression": "2*2"}, "output_key": "out_1"}]
        },
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]

    arc_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows/{wf_id}/archive?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )
    assert arc_res.status_code == 200
    assert arc_res.json()["status"] == "ARCHIVED"

    # Updating archived workflow must fail
    up_res = await async_client.patch(
        f"{settings.API_V1_STR}/workflows/{wf_id}?org_id={t['org_id']}",
        json={"name": "Will Fail"},
        headers=t["manager"]["headers"],
    )
    assert up_res.status_code == 400


@pytest.mark.asyncio
async def test_07_execute_workflow(wf_tenant, async_client: AsyncClient):
    """7. Start workflow execution creates PENDING execution record."""
    t = wf_tenant
    # Create and activate
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={
            "name": "Exec Target",
            "steps": [{"name": "Calc", "type": "CALCULATOR", "configuration": {"expression": "100/4"}, "output_key": "ans"}]
        },
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]
    await async_client.post(
        f"{settings.API_V1_STR}/workflows/{wf_id}/activate?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )

    ex_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['org_id']}",
        json={"initial_inputs": {"user_param": 42}},
        headers=t["member"]["headers"],
    )
    assert ex_res.status_code == 201
    data = ex_res.json()
    assert data["status"] == "PENDING"
    assert data["context_data"]["inputs"]["user_param"] == 42


@pytest.mark.asyncio
async def test_08_sequential_execution(wf_tenant):
    """8. Workflow engine runs sequential steps and passes output forward."""
    t = wf_tenant
    async with db_module.async_session_maker() as session:
        wf = await workflow_service.create_workflow(
            db=session,
            organization_id=t["org_id"],
            created_by=t["manager"]["id"],
            workflow_in=WorkflowCreate(
                name="Sequential Math Pipeline",
                steps=[
                    WorkflowStepCreate(
                        name="Step 1 Calc",
                        type=StepType.CALCULATOR,
                        order=0,
                        configuration={"expression": "10 * 5"},
                        output_key="first_calc",
                    ),
                    WorkflowStepCreate(
                        name="Step 2 Calc",
                        type=StepType.CALCULATOR,
                        order=1,
                        configuration={"expression": "100 + 50"},
                        output_key="second_calc",
                    ),
                ]
            )
        )
        await workflow_service.activate_workflow(session, wf.id, t["org_id"])
        execution = await workflow_service.start_execution(
            session, wf.id, t["org_id"], t["member"]["id"], initial_inputs={}
        )
        exec_id = execution.id

    # Run engine generator to completion
    events = []
    async for event in WorkflowEngine.run_execution(
        execution_id=exec_id,
        organization_id=t["org_id"],
        user_id=t["member"]["id"],
        user_role="MEMBER",
    ):
        events.append(event)

    event_names = [e["event"] for e in events]
    assert "workflow_start" in event_names
    assert "workflow_step_complete" in event_names
    assert "workflow_complete" in event_names

    # Check final context in database
    async with db_module.async_session_maker() as session:
        completed_exec = await workflow_service.get_execution(session, exec_id, t["org_id"])
        assert completed_exec.status == ExecutionStatus.COMPLETED
        assert "first_calc" in completed_exec.context_data
        assert "second_calc" in completed_exec.context_data


@pytest.mark.asyncio
async def test_09_state_persistence(wf_tenant):
    """9. Workflow step executions and context are durably persisted in PostgreSQL."""
    t = wf_tenant
    async with db_module.async_session_maker() as session:
        wf = await workflow_service.create_workflow(
            db=session,
            organization_id=t["org_id"],
            created_by=t["manager"]["id"],
            workflow_in=WorkflowCreate(
                name="Persistence Test",
                steps=[
                    WorkflowStepCreate(
                        name="Stats",
                        type=StepType.ORGANIZATION_STATS,
                        output_key="persisted_stats",
                    )
                ]
            )
        )
        await workflow_service.activate_workflow(session, wf.id, t["org_id"])
        execution = await workflow_service.start_execution(
            session, wf.id, t["org_id"], t["member"]["id"], initial_inputs={"source": "test09"}
        )
        exec_id = execution.id

    async for _ in WorkflowEngine.run_execution(exec_id, t["org_id"], t["manager"]["id"], "MANAGER"):
        pass

    async with db_module.async_session_maker() as session:
        res = await workflow_service.get_execution(session, exec_id, t["org_id"])
        assert res.status == ExecutionStatus.COMPLETED
        assert len(res.step_executions) == 1
        assert res.step_executions[0].status == StepExecutionStatus.COMPLETED
        assert "persisted_stats" in res.context_data


@pytest.mark.asyncio
async def test_10_resume_after_failure(wf_tenant):
    """10. Resumed workflow skips already completed steps."""
    t = wf_tenant
    async with db_module.async_session_maker() as session:
        wf = await workflow_service.create_workflow(
            db=session,
            organization_id=t["org_id"],
            created_by=t["manager"]["id"],
            workflow_in=WorkflowCreate(
                name="Resume Test",
                steps=[
                    WorkflowStepCreate(
                        name="Step One",
                        type=StepType.CALCULATOR,
                        order=0,
                        configuration={"expression": "1 + 1"},
                        output_key="step_1",
                    ),
                    WorkflowStepCreate(
                        name="Step Two",
                        type=StepType.CALCULATOR,
                        order=1,
                        configuration={"expression": "2 + 2"},
                        output_key="step_2",
                    )
                ]
            )
        )
        await workflow_service.activate_workflow(session, wf.id, t["org_id"])
        execution = await workflow_service.start_execution(
            session, wf.id, t["org_id"], t["member"]["id"], initial_inputs={}
        )
        exec_id = execution.id

        # Manually mark step 1 as completed beforehand
        s1 = wf.steps[0]
        step1_exec = WorkflowStepExecution(
            execution_id=exec_id,
            step_id=s1.id,
            status=StepExecutionStatus.COMPLETED,
            inputs={},
            outputs={"result": 2},
        )
        session.add(step1_exec)
        execution.context_data = {"step_1": {"result": 2}}
        await session.commit()

    # Run engine: should skip Step 1 and execute Step 2
    step_starts = []
    async for event in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        if event.get("event") == "workflow_step_start":
            step_starts.append(event["data"]["step_name"])

    assert "Step Two" in step_starts
    assert "Step One" not in step_starts


@pytest.mark.asyncio
async def test_11_retry_logic(wf_tenant):
    """11. Configurable retry count records retry attempts on failures."""
    t = wf_tenant
    async with db_module.async_session_maker() as session:
        wf = await workflow_service.create_workflow(
            db=session,
            organization_id=t["org_id"],
            created_by=t["manager"]["id"],
            workflow_in=WorkflowCreate(
                name="Retry Test",
                steps=[
                    WorkflowStepCreate(
                        name="Failing Calc",
                        type=StepType.CALCULATOR,
                        configuration={"expression": "invalid_expression / 0"},
                        retry_count=2,
                        output_key="err_out",
                    )
                ]
            )
        )
        await workflow_service.activate_workflow(session, wf.id, t["org_id"])
        execution = await workflow_service.start_execution(
            session, wf.id, t["org_id"], t["member"]["id"], initial_inputs={}
        )
        exec_id = execution.id

    events = []
    async for event in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        events.append(event)

    async with db_module.async_session_maker() as session:
        res = await workflow_service.get_execution(session, exec_id, t["org_id"])
        assert res.status == ExecutionStatus.FAILED
        assert res.step_executions[0].retry_attempts == 2


@pytest.mark.asyncio
async def test_12_conditional_branching(wf_tenant):
    """12. Condition evaluating to False skips step."""
    t = wf_tenant
    async with db_module.async_session_maker() as session:
        wf = await workflow_service.create_workflow(
            db=session,
            organization_id=t["org_id"],
            created_by=t["manager"]["id"],
            workflow_in=WorkflowCreate(
                name="Conditional Branching Test",
                steps=[
                    WorkflowStepCreate(
                        name="Step True",
                        type=StepType.CALCULATOR,
                        order=0,
                        configuration={"expression": "10 * 10"},
                        output_key="step_true",
                        condition={"field": "inputs.run_true", "operator": "==", "value": True},
                    ),
                    WorkflowStepCreate(
                        name="Step False",
                        type=StepType.CALCULATOR,
                        order=1,
                        configuration={"expression": "20 * 20"},
                        output_key="step_false",
                        condition={"field": "inputs.run_true", "operator": "==", "value": False},
                    ),
                ]
            )
        )
        await workflow_service.activate_workflow(session, wf.id, t["org_id"])
        execution = await workflow_service.start_execution(
            session, wf.id, t["org_id"], t["member"]["id"], initial_inputs={"run_true": True}
        )
        exec_id = execution.id

    async for _ in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        pass

    async with db_module.async_session_maker() as session:
        res = await workflow_service.get_execution(session, exec_id, t["org_id"])
        assert res.status == ExecutionStatus.COMPLETED
        assert "step_true" in res.context_data
        assert "step_false" not in res.context_data


@pytest.mark.asyncio
async def test_13_invalid_condition_rejected(wf_tenant):
    """13. Malformed condition raises InvalidConditionError."""
    with pytest.raises(InvalidConditionError):
        SafeConditionEvaluator.evaluate({"field": "score", "operator": "INVALID_OP", "value": 10}, {})


@pytest.mark.asyncio
async def test_14_arbitrary_python_rejected(wf_tenant):
    """14. Arbitrary Python/eval execution is strictly blocked."""
    with pytest.raises(InvalidConditionError):
        SafeConditionEvaluator.evaluate("eval('import os; os.system()')", {})


@pytest.mark.asyncio
async def test_15_arbitrary_sql_rejected(wf_tenant, async_client: AsyncClient):
    """15. SQL injection tokens in configuration are rejected."""
    t = wf_tenant
    payload = {
        "name": "SQL Attack Workflow",
        "steps": [
            {
                "name": "Injection Step",
                "type": "CALCULATOR",
                "configuration": {"expression": "1; DROP TABLE workflows; --"},
                "output_key": "hack",
            }
        ]
    }
    res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json=payload,
        headers=t["manager"]["headers"],
    )
    assert res.status_code == 400
    assert "forbidden" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_16_unknown_tool_rejected(wf_tenant, async_client: AsyncClient):
    """16. Unknown step type rejected by schema validation."""
    t = wf_tenant
    payload = {
        "name": "Unknown Step Workflow",
        "steps": [
            {
                "name": "Bad Step",
                "type": "UNKNOWN_TOOL_TYPE",
                "output_key": "bad",
            }
        ]
    }
    res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json=payload,
        headers=t["manager"]["headers"],
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_17_cross_tenant_workflow_blocked(wf_tenant, async_client: AsyncClient):
    """17. Tenant B cannot access Tenant A's workflow."""
    t = wf_tenant
    # Get Tenant A workflow
    list_res = await async_client.get(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )
    wf_id = list_res.json()["items"][0]["id"]

    # Tenant B requests it
    res = await async_client.get(
        f"{settings.API_V1_STR}/workflows/{wf_id}?org_id={t['tenant_b']['org_id']}",
        headers=t["tenant_b"]["headers"],
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_18_cross_tenant_execution_blocked(wf_tenant, async_client: AsyncClient):
    """18. Tenant B cannot execute or view Tenant A's workflow execution."""
    t = wf_tenant
    # List Tenant A workflows
    list_res = await async_client.get(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )
    wf_id = list_res.json()["items"][0]["id"]

    # Tenant B tries to execute Tenant A's workflow
    res = await async_client.post(
        f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['tenant_b']['org_id']}",
        json={"initial_inputs": {}},
        headers=t["tenant_b"]["headers"],
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_19_unauthorized_execution_blocked(wf_tenant, async_client: AsyncClient):
    """19. Non-member cannot execute workflow."""
    t = wf_tenant
    list_res = await async_client.get(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )
    wf_id = list_res.json()["items"][0]["id"]

    # Outsider token against Tenant A org_id
    res = await async_client.post(
        f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['org_id']}",
        json={"initial_inputs": {}},
        headers=t["tenant_b"]["headers"],
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_20_pause_execution(wf_tenant, async_client: AsyncClient):
    """20. Pause a workflow execution."""
    t = wf_tenant
    # Create active workflow & start execution
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={"name": "Pause WF", "steps": [{"name": "Calc", "type": "CALCULATOR", "output_key": "c"}]},
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]
    await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/activate?org_id={t['org_id']}", headers=t["manager"]["headers"])
    ex_res = await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['org_id']}", headers=t["member"]["headers"])
    exec_id = ex_res.json()["id"]

    p_res = await async_client.post(
        f"{settings.API_V1_STR}/workflow-executions/{exec_id}/pause?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert p_res.status_code == 200
    assert p_res.json()["status"] == "PAUSED"


@pytest.mark.asyncio
async def test_21_resume_execution(wf_tenant, async_client: AsyncClient):
    """21. Resume a paused workflow execution."""
    t = wf_tenant
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={"name": "Resume WF", "steps": [{"name": "Calc", "type": "CALCULATOR", "output_key": "c"}]},
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]
    await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/activate?org_id={t['org_id']}", headers=t["manager"]["headers"])
    ex_res = await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['org_id']}", headers=t["member"]["headers"])
    exec_id = ex_res.json()["id"]

    await async_client.post(f"{settings.API_V1_STR}/workflow-executions/{exec_id}/pause?org_id={t['org_id']}", headers=t["member"]["headers"])
    r_res = await async_client.post(
        f"{settings.API_V1_STR}/workflow-executions/{exec_id}/resume?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert r_res.status_code == 200
    assert r_res.json()["status"] == "RUNNING"


@pytest.mark.asyncio
async def test_22_cancel_execution(wf_tenant, async_client: AsyncClient):
    """22. Cancel a workflow execution."""
    t = wf_tenant
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={"name": "Cancel WF", "steps": [{"name": "Calc", "type": "CALCULATOR", "output_key": "c"}]},
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]
    await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/activate?org_id={t['org_id']}", headers=t["manager"]["headers"])
    ex_res = await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['org_id']}", headers=t["member"]["headers"])
    exec_id = ex_res.json()["id"]

    can_res = await async_client.post(
        f"{settings.API_V1_STR}/workflow-executions/{exec_id}/cancel?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert can_res.status_code == 200
    assert can_res.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_23_approval_required_step_pauses(wf_tenant):
    """23. Step requiring human approval pauses execution and creates Phase 10 approval."""
    t = wf_tenant
    async with db_module.async_session_maker() as session:
        wf = await workflow_service.create_workflow(
            db=session,
            organization_id=t["org_id"],
            created_by=t["manager"]["id"],
            workflow_in=WorkflowCreate(
                name="HITL Workflow",
                steps=[
                    WorkflowStepCreate(
                        name="Create Note Step",
                        type=StepType.DEMO_NOTE,
                        configuration={"title": "Q3 Targets", "content": "Initial targets draft"},
                        output_key="note_result",
                        requires_approval=True,
                    )
                ]
            )
        )
        await workflow_service.activate_workflow(session, wf.id, t["org_id"])
        execution = await workflow_service.start_execution(
            session, wf.id, t["org_id"], t["member"]["id"], initial_inputs={}
        )
        exec_id = execution.id

    events = []
    async for event in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        events.append(event)

    event_names = [e["event"] for e in events]
    assert "workflow_waiting_approval" in event_names

    async with db_module.async_session_maker() as session:
        res = await workflow_service.get_execution(session, exec_id, t["org_id"])
        assert res.status == ExecutionStatus.WAITING_APPROVAL
        step_exec = res.step_executions[0]
        assert step_exec.status == StepExecutionStatus.WAITING_APPROVAL
        assert step_exec.approval_id is not None

        # Verify Phase 10 approval record exists
        appr = await approval_service.get_approval(session, step_exec.approval_id, t["org_id"])
        assert appr.status == ApprovalStatus.PENDING


@pytest.mark.asyncio
async def test_24_approved_step_executes(wf_tenant):
    """24. Approved workflow step executes and completes workflow upon resume."""
    t = wf_tenant
    async with db_module.async_session_maker() as session:
        wf = await workflow_service.create_workflow(
            db=session,
            organization_id=t["org_id"],
            created_by=t["manager"]["id"],
            workflow_in=WorkflowCreate(
                name="Approved Exec Test",
                steps=[
                    WorkflowStepCreate(
                        name="Note Step",
                        type=StepType.DEMO_NOTE,
                        configuration={"title": "Approved Note", "content": "Body"},
                        output_key="note_out",
                        requires_approval=True,
                    )
                ]
            )
        )
        await workflow_service.activate_workflow(session, wf.id, t["org_id"])
        execution = await workflow_service.start_execution(
            session, wf.id, t["org_id"], t["member"]["id"], initial_inputs={}
        )
        exec_id = execution.id

    # 1. First run: pauses at approval
    async for _ in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        pass

    # 2. Approve via Phase 10 approval service
    async with db_module.async_session_maker() as session:
        ex = await workflow_service.get_execution(session, exec_id, t["org_id"])
        appr_id = ex.step_executions[0].approval_id
        await approval_service.approve(session, appr_id, t["org_id"], t["manager"]["id"], "MANAGER")

    # 3. Resume and complete
    async for _ in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        pass

    async with db_module.async_session_maker() as session:
        final_ex = await workflow_service.get_execution(session, exec_id, t["org_id"])
        assert final_ex.status == ExecutionStatus.COMPLETED
        assert "note_out" in final_ex.context_data


@pytest.mark.asyncio
async def test_25_rejected_step_does_not_execute(wf_tenant):
    """25. Rejected approval blocks step execution and fails workflow."""
    t = wf_tenant
    async with db_module.async_session_maker() as session:
        wf = await workflow_service.create_workflow(
            db=session,
            organization_id=t["org_id"],
            created_by=t["manager"]["id"],
            workflow_in=WorkflowCreate(
                name="Reject Exec Test",
                steps=[
                    WorkflowStepCreate(
                        name="Note Step",
                        type=StepType.DEMO_NOTE,
                        configuration={"title": "Rejected Note", "content": "Body"},
                        output_key="note_out",
                        requires_approval=True,
                    )
                ]
            )
        )
        await workflow_service.activate_workflow(session, wf.id, t["org_id"])
        execution = await workflow_service.start_execution(
            session, wf.id, t["org_id"], t["member"]["id"], initial_inputs={}
        )
        exec_id = execution.id

    # First run: pauses
    async for _ in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        pass

    # Reject via Phase 10 approval service
    async with db_module.async_session_maker() as session:
        ex = await workflow_service.get_execution(session, exec_id, t["org_id"])
        appr_id = ex.step_executions[0].approval_id
        await approval_service.reject(session, appr_id, t["org_id"], t["manager"]["id"], "MANAGER", "Denied by security policy")

    # Resume run: encounters rejected status
    async for _ in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        pass

    async with db_module.async_session_maker() as session:
        final_ex = await workflow_service.get_execution(session, exec_id, t["org_id"])
        assert final_ex.status == ExecutionStatus.FAILED
        assert "rejected" in final_ex.error.lower()


@pytest.mark.asyncio
async def test_26_expired_approval_blocks_execution(wf_tenant):
    """26. Expired approval blocks execution."""
    t = wf_tenant
    async with db_module.async_session_maker() as session:
        wf = await workflow_service.create_workflow(
            db=session,
            organization_id=t["org_id"],
            created_by=t["manager"]["id"],
            workflow_in=WorkflowCreate(
                name="Expired Exec Test",
                steps=[
                    WorkflowStepCreate(
                        name="Note Step",
                        type=StepType.DEMO_NOTE,
                        configuration={"title": "Expired Note", "content": "Body"},
                        output_key="note_out",
                        requires_approval=True,
                    )
                ]
            )
        )
        await workflow_service.activate_workflow(session, wf.id, t["org_id"])
        execution = await workflow_service.start_execution(
            session, wf.id, t["org_id"], t["member"]["id"], initial_inputs={}
        )
        exec_id = execution.id

    async for _ in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        pass

    # Manually expire approval in DB
    async with db_module.async_session_maker() as session:
        ex = await workflow_service.get_execution(session, exec_id, t["org_id"])
        appr_id = ex.step_executions[0].approval_id
        appr = await session.get(Approval, appr_id)
        appr.status = ApprovalStatus.EXPIRED
        await session.commit()

    async for _ in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        pass

    async with db_module.async_session_maker() as session:
        final_ex = await workflow_service.get_execution(session, exec_id, t["org_id"])
        assert final_ex.status == ExecutionStatus.FAILED
        assert "expired" in final_ex.error.lower()


@pytest.mark.asyncio
async def test_27_duplicate_execution_protection(wf_tenant):
    """27. Completed execution cannot be executed again."""
    t = wf_tenant
    async with db_module.async_session_maker() as session:
        wf = await workflow_service.create_workflow(
            db=session,
            organization_id=t["org_id"],
            created_by=t["manager"]["id"],
            workflow_in=WorkflowCreate(
                name="Dup Protection",
                steps=[WorkflowStepCreate(name="Calc", type=StepType.CALCULATOR, configuration={"expression": "100 + 50"}, output_key="c")]
            )
        )
        await workflow_service.activate_workflow(session, wf.id, t["org_id"])
        execution = await workflow_service.start_execution(
            session, wf.id, t["org_id"], t["member"]["id"], initial_inputs={}
        )
        exec_id = execution.id

    # Run once to completion
    async for _ in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
        pass

    # Trying to run again raises WorkflowStateError
    with pytest.raises(WorkflowStateError):
        async for _ in WorkflowEngine.run_execution(exec_id, t["org_id"], t["member"]["id"], "MEMBER"):
            pass


@pytest.mark.asyncio
async def test_28_invalid_state_transition(wf_tenant, async_client: AsyncClient):
    """28. Invalid state transition raises HTTP 400."""
    t = wf_tenant
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={"name": "State Error WF", "steps": [{"name": "Calc", "type": "CALCULATOR", "output_key": "c"}]},
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]
    await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/activate?org_id={t['org_id']}", headers=t["manager"]["headers"])
    ex_res = await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['org_id']}", headers=t["member"]["headers"])
    exec_id = ex_res.json()["id"]

    # Cancel execution
    await async_client.post(f"{settings.API_V1_STR}/workflow-executions/{exec_id}/cancel?org_id={t['org_id']}", headers=t["member"]["headers"])

    # Attempting to resume a CANCELLED execution must return 400
    res = await async_client.post(
        f"{settings.API_V1_STR}/workflow-executions/{exec_id}/resume?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_29_sse_workflow_start(wf_tenant, async_client: AsyncClient):
    """29. SSE stream emits workflow_start event."""
    t = wf_tenant
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={"name": "SSE Start WF", "steps": [{"name": "Calc", "type": "CALCULATOR", "output_key": "c"}]},
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]
    await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/activate?org_id={t['org_id']}", headers=t["manager"]["headers"])
    ex_res = await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['org_id']}", headers=t["member"]["headers"])
    exec_id = ex_res.json()["id"]

    stream_res = await async_client.get(
        f"{settings.API_V1_STR}/workflow-executions/{exec_id}/stream?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert stream_res.status_code == 200
    assert "event: workflow_start" in stream_res.text


@pytest.mark.asyncio
async def test_30_sse_workflow_step_complete(wf_tenant, async_client: AsyncClient):
    """30. SSE stream emits workflow_step_complete event."""
    t = wf_tenant
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={"name": "SSE Step WF", "steps": [{"name": "Calc", "type": "CALCULATOR", "configuration": {"expression": "5 * 5"}, "output_key": "c"}]},
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]
    await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/activate?org_id={t['org_id']}", headers=t["manager"]["headers"])
    ex_res = await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['org_id']}", headers=t["member"]["headers"])
    exec_id = ex_res.json()["id"]

    stream_res = await async_client.get(
        f"{settings.API_V1_STR}/workflow-executions/{exec_id}/stream?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert stream_res.status_code == 200
    assert "event: workflow_step_complete" in stream_res.text


@pytest.mark.asyncio
async def test_31_sse_workflow_waiting_approval(wf_tenant, async_client: AsyncClient):
    """31. SSE stream emits workflow_waiting_approval for sensitive step."""
    t = wf_tenant
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={
            "name": "SSE Approval WF",
            "steps": [
                {
                    "name": "Note Step",
                    "type": "DEMO_NOTE",
                    "configuration": {"title": "SSE Note", "content": "Body"},
                    "output_key": "note_out",
                    "requires_approval": True,
                }
            ]
        },
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]
    await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/activate?org_id={t['org_id']}", headers=t["manager"]["headers"])
    ex_res = await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['org_id']}", headers=t["member"]["headers"])
    exec_id = ex_res.json()["id"]

    stream_res = await async_client.get(
        f"{settings.API_V1_STR}/workflow-executions/{exec_id}/stream?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert stream_res.status_code == 200
    assert "event: workflow_waiting_approval" in stream_res.text


@pytest.mark.asyncio
async def test_32_sse_workflow_complete(wf_tenant, async_client: AsyncClient):
    """32. SSE stream emits workflow_complete event upon finishing all steps."""
    t = wf_tenant
    c_res = await async_client.post(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        json={"name": "SSE Complete WF", "steps": [{"name": "Calc", "type": "CALCULATOR", "configuration": {"expression": "10 * 10"}, "output_key": "c"}]},
        headers=t["manager"]["headers"],
    )
    wf_id = c_res.json()["id"]
    await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/activate?org_id={t['org_id']}", headers=t["manager"]["headers"])
    ex_res = await async_client.post(f"{settings.API_V1_STR}/workflows/{wf_id}/execute?org_id={t['org_id']}", headers=t["member"]["headers"])
    exec_id = ex_res.json()["id"]

    stream_res = await async_client.get(
        f"{settings.API_V1_STR}/workflow-executions/{exec_id}/stream?org_id={t['org_id']}",
        headers=t["member"]["headers"],
    )
    assert stream_res.status_code == 200
    assert "event: workflow_complete" in stream_res.text


@pytest.mark.asyncio
async def test_33_no_secret_leakage(wf_tenant, async_client: AsyncClient):
    """33. Workflow endpoints and SSE streams do not leak secrets or credentials."""
    t = wf_tenant
    list_res = await async_client.get(
        f"{settings.API_V1_STR}/workflows?org_id={t['org_id']}",
        headers=t["manager"]["headers"],
    )
    assert list_res.status_code == 200
    text_content = list_res.text.lower()

    forbidden_terms = [
        "jwt_secret",
        "openai_api_key",
        "gemini_api_key",
        "password",
        "system_instruction",
        "chain_of_thought",
    ]
    for term in forbidden_terms:
        assert term not in text_content
