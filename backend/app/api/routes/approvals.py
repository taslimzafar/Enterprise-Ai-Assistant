from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_db,
    get_current_active_user,
    RoleChecker,
)
from app.db.models.user import User
from app.db.models.membership import Membership, RoleEnum
from app.db.models.approval import ApprovalStatus
from app.services.approval.schemas import (
    ApprovalResponse,
    ApprovalListResponse,
    ApprovalAction,
)
from app.services.approval.service import approval_service
from app.services.approval.exceptions import (
    ApprovalNotFoundError,
    CrossTenantAccessError,
    ApprovalPermissionDeniedError,
    SelfApprovalForbiddenError,
    InvalidStateTransitionError,
    ApprovalExpiredError,
)

router = APIRouter(prefix="/approvals", tags=["approvals"])

require_viewer = RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER, RoleEnum.MEMBER])
require_manager = RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER])


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    org_id: str = Query(..., description="Organization ID"),
    status_filter: Optional[ApprovalStatus] = Query(None, alias="status", description="Filter by approval status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(require_viewer),
):
    """List approval requests within an organization with optional status filtering."""
    # Organization boundary verified by require_viewer dependency
    items, total = await approval_service.list_approvals(
        db=db,
        organization_id=org_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return ApprovalListResponse(items=items, total=total)


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(require_viewer),
):
    """Retrieve details of a specific approval request within the organization."""
    try:
        approval = await approval_service.get_approval(
            db=db,
            approval_id=approval_id,
            organization_id=org_id,
        )
        return approval
    except ApprovalNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_id}' not found.",
        )
    except CrossTenantAccessError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access forbidden.",
        )


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve_request(
    approval_id: str,
    org_id: str = Query(..., description="Organization ID"),
    payload: Optional[ApprovalAction] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_manager),
):
    """Approve a pending approval request. Requester cannot approve their own request."""
    user_role = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
    try:
        approved = await approval_service.approve(
            db=db,
            approval_id=approval_id,
            organization_id=org_id,
            approver_user_id=current_user.id,
            approver_role=user_role,
        )
        return approved
    except ApprovalNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_id}' not found.",
        )
    except CrossTenantAccessError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant mutation forbidden.",
        )
    except SelfApprovalForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except ApprovalPermissionDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except (InvalidStateTransitionError, ApprovalExpiredError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
async def reject_request(
    approval_id: str,
    org_id: str = Query(..., description="Organization ID"),
    payload: Optional[ApprovalAction] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_manager),
):
    """Reject a pending approval request."""
    user_role = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
    rejection_reason = payload.rejection_reason if payload else None
    try:
        rejected = await approval_service.reject(
            db=db,
            approval_id=approval_id,
            organization_id=org_id,
            approver_user_id=current_user.id,
            approver_role=user_role,
            rejection_reason=rejection_reason,
        )
        return rejected
    except ApprovalNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_id}' not found.",
        )
    except CrossTenantAccessError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant mutation forbidden.",
        )
    except ApprovalPermissionDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except (InvalidStateTransitionError, ApprovalExpiredError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{approval_id}/cancel", response_model=ApprovalResponse)
async def cancel_request(
    approval_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    membership: Membership = Depends(require_viewer),
):
    """Cancel a pending approval request (by the original requester or a manager)."""
    user_role = membership.role.value if hasattr(membership.role, "value") else str(membership.role)
    try:
        cancelled = await approval_service.cancel(
            db=db,
            approval_id=approval_id,
            organization_id=org_id,
            user_id=current_user.id,
            user_role=user_role,
        )
        return cancelled
    except ApprovalNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval '{approval_id}' not found.",
        )
    except CrossTenantAccessError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant mutation forbidden.",
        )
    except ApprovalPermissionDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )
    except (InvalidStateTransitionError, ApprovalExpiredError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
