from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import (
    RoleChecker,
)
from app.db.models.membership import Membership, RoleEnum
from app.services.observability import observability_service
from app.services.observability.traces import TraceModel

router = APIRouter(prefix="/observability", tags=["observability"])

ALL_ROLES = [RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER, RoleEnum.MEMBER, RoleEnum.VIEWER]
require_member = RoleChecker(ALL_ROLES)


@router.get("/metrics")
async def get_observability_metrics(
    org_id: str = Query(..., description="Organization ID"),
    membership: Membership = Depends(require_member),
):
    """Retrieve operational observability metrics for the tenant."""
    # Enforces organization isolation
    return observability_service.get_metrics(organization_id=org_id)


@router.get("/traces/{trace_id}", response_model=TraceModel)
async def get_trace_details(
    trace_id: str,
    org_id: str = Query(..., description="Organization ID"),
    membership: Membership = Depends(require_member),
):
    """Retrieve trace and span execution tree for a specific request."""
    trace = observability_service.get_trace(trace_id=trace_id, organization_id=org_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trace not found or does not belong to organization",
        )
    return trace
