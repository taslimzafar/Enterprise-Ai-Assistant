from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_db,
    get_current_active_user,
    get_current_membership,
    RoleChecker,
)
from app.db.models.user import User
from app.db.models.membership import Membership, RoleEnum
from app.db.models.workflow import WorkflowStatus
from app.services.workflow.schemas import (
    WorkflowCreate,
    WorkflowUpdate,
    WorkflowResponse,
    WorkflowListResponse,
    WorkflowExecutionCreate,
    WorkflowExecutionResponse,
    WorkflowExecutionListResponse,
)
from app.services.workflow.service import workflow_service
from app.services.workflow.executor import WorkflowStreamingExecutor
from app.services.workflow.exceptions import (
    WorkflowNotFoundError,
    WorkflowExecutionNotFoundError,
    WorkflowValidationError,
    WorkflowStateError,
    InvalidStateTransitionError,
    InvalidConditionError,
)

from app.core.rate_limit import rate_limiter
from app.core.config import settings

router = APIRouter()

# Role permissions
MANAGERS_ONLY = RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER])
MEMBERS_ALLOWED = RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER, RoleEnum.MEMBER])
ALL_ROLES = RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER, RoleEnum.MEMBER, RoleEnum.VIEWER])


@router.post(
    "/workflows",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workflow definition",
)
async def create_workflow(
    workflow_in: WorkflowCreate,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(MANAGERS_ONLY),
):
    try:
        wf = await workflow_service.create_workflow(
            db=db,
            organization_id=org_id,
            created_by=current_user.id,
            workflow_in=workflow_in,
        )
        return wf
    except WorkflowValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/workflows",
    response_model=WorkflowListResponse,
    summary="List workflows in organization",
)
async def list_workflows(
    org_id: str = Query(..., description="Organization ID"),
    status_filter: Optional[WorkflowStatus] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(ALL_ROLES),
):
    items, total = await workflow_service.list_workflows(
        db=db,
        organization_id=org_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total}


@router.get(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get workflow definition by ID",
)
async def get_workflow(
    workflow_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(ALL_ROLES),
):
    try:
        wf = await workflow_service.get_workflow(db, workflow_id, org_id)
        return wf
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch(
    "/workflows/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Update workflow definition",
)
async def update_workflow(
    workflow_id: str,
    workflow_update: WorkflowUpdate,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(MANAGERS_ONLY),
):
    try:
        wf = await workflow_service.update_workflow(
            db=db,
            workflow_id=workflow_id,
            organization_id=org_id,
            workflow_update=workflow_update,
        )
        return wf
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (WorkflowValidationError, WorkflowStateError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/workflows/{workflow_id}/activate",
    response_model=WorkflowResponse,
    summary="Activate workflow",
)
async def activate_workflow(
    workflow_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(MANAGERS_ONLY),
):
    try:
        wf = await workflow_service.activate_workflow(db, workflow_id, org_id)
        return wf
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (WorkflowValidationError, WorkflowStateError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/workflows/{workflow_id}/archive",
    response_model=WorkflowResponse,
    summary="Archive workflow",
)
async def archive_workflow(
    workflow_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(MANAGERS_ONLY),
):
    try:
        wf = await workflow_service.archive_workflow(db, workflow_id, org_id)
        return wf
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/workflows/{workflow_id}/execute",
    response_model=WorkflowExecutionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start workflow execution",
)
async def execute_workflow(
    workflow_id: str,
    execution_in: Optional[WorkflowExecutionCreate] = None,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(MEMBERS_ALLOWED),
):
    await rate_limiter.check(
        f"workflow:execute:{org_id}:{current_user.id}",
        limit=settings.RATE_LIMIT_WORKFLOW_PER_MINUTE,
    )
    try:
        inputs = execution_in.initial_inputs if execution_in else {}
        execution = await workflow_service.start_execution(
            db=db,
            workflow_id=workflow_id,
            organization_id=org_id,
            executed_by=current_user.id,
            initial_inputs=inputs,
        )
        return execution
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except WorkflowStateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/workflows/{workflow_id}/executions",
    response_model=WorkflowExecutionListResponse,
    summary="List executions of a workflow",
)
async def list_executions(
    workflow_id: str,
    org_id: str = Query(..., description="Organization ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(ALL_ROLES),
):
    try:
        # Check workflow exists
        await workflow_service.get_workflow(db, workflow_id, org_id)
        items, total = await workflow_service.list_executions(
            db=db,
            workflow_id=workflow_id,
            organization_id=org_id,
            limit=limit,
            offset=offset,
        )
        return {"items": items, "total": total}
    except WorkflowNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/workflow-executions/{execution_id}",
    response_model=WorkflowExecutionResponse,
    summary="Get execution details",
)
async def get_execution(
    execution_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(ALL_ROLES),
):
    try:
        execution = await workflow_service.get_execution(db, execution_id, org_id)
        return execution
    except WorkflowExecutionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/workflow-executions/{execution_id}/pause",
    response_model=WorkflowExecutionResponse,
    summary="Pause running execution",
)
async def pause_execution(
    execution_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(MEMBERS_ALLOWED),
):
    try:
        execution = await workflow_service.pause_execution(db, execution_id, org_id)
        return execution
    except WorkflowExecutionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/workflow-executions/{execution_id}/resume",
    response_model=WorkflowExecutionResponse,
    summary="Resume paused execution",
)
async def resume_execution(
    execution_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(MEMBERS_ALLOWED),
):
    try:
        execution = await workflow_service.resume_execution(db, execution_id, org_id)
        return execution
    except WorkflowExecutionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/workflow-executions/{execution_id}/cancel",
    response_model=WorkflowExecutionResponse,
    summary="Cancel execution",
)
async def cancel_execution(
    execution_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(MEMBERS_ALLOWED),
):
    try:
        execution = await workflow_service.cancel_execution(db, execution_id, org_id)
        return execution
    except WorkflowExecutionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStateTransitionError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/workflow-executions/{execution_id}/stream",
    summary="Stream workflow execution events (SSE)",
)
async def stream_workflow_execution(
    execution_id: str,
    org_id: str = Query(..., description="Organization ID"),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(MEMBERS_ALLOWED),
):
    """Server-Sent Events streaming endpoint for workflow execution."""
    return StreamingResponse(
        WorkflowStreamingExecutor.stream_execution(
            execution_id=execution_id,
            organization_id=org_id,
            user_id=current_user.id,
            user_role=membership.role.value,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
