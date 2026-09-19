from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_db,
    get_current_active_user,
    RoleChecker,
)
from app.db.models.user import User
from app.db.models.membership import Membership, RoleEnum
from app.services.evaluation.service import evaluation_service
from app.services.evaluation.schemas import (
    EvaluationRunRequest,
    EvaluationRunResponse,
    EvaluationRecordResponse,
    EvaluationMetricsResponse,
    EvaluationDatasetSchema,
)

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

ALL_ROLES = [RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER, RoleEnum.MEMBER, RoleEnum.VIEWER]
ADMIN_ROLES = [RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER]

require_member = RoleChecker(ALL_ROLES)
require_manager = RoleChecker(ADMIN_ROLES)


@router.post("/run", response_model=EvaluationRunResponse, status_code=status.HTTP_201_CREATED)
async def run_evaluation(
    request: EvaluationRunRequest,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(require_manager),
    current_user: User = Depends(get_current_active_user),
):
    """Trigger an evaluation run against a dataset for the tenant."""
    try:
        run = await evaluation_service.run_evaluation(
            db=db,
            organization_id=org_id,
            user_id=current_user.id,
            request=request,
        )
        return run
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("", response_model=List[EvaluationRunResponse])
async def list_evaluations(
    org_id: str = Query(..., description="Organization ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(require_member),
):
    """List historical evaluation runs for the organization."""
    runs, _ = await evaluation_service.list_runs(
        db=db,
        organization_id=org_id,
        limit=limit,
        offset=offset,
    )
    return runs


@router.get("/metrics", response_model=EvaluationMetricsResponse)
async def get_evaluation_metrics(
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(require_member),
):
    """Get aggregated evaluation metrics and latency percentiles for the organization."""
    return await evaluation_service.get_metrics(db=db, organization_id=org_id)


@router.get("/datasets", response_model=List[EvaluationDatasetSchema])
async def list_evaluation_datasets(
    org_id: str = Query(..., description="Organization ID"),
    membership: Membership = Depends(require_member),
):
    """List available evaluation datasets and their test cases."""
    return evaluation_service.list_datasets()


@router.get("/{evaluation_id}", response_model=EvaluationRunResponse)
async def get_evaluation_details(
    evaluation_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(require_member),
):
    """Get detailed information and test case records for a specific evaluation run."""
    run = await evaluation_service.get_run_details(
        db=db,
        organization_id=org_id,
        run_id=evaluation_id,
    )
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation run not found or does not belong to organization",
        )
    return run
