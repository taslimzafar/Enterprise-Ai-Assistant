import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from sqlalchemy import select, func, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models.approval import Approval, ApprovalStatus
from app.services.approval.permissions import ApprovalPermissionChecker
from app.services.approval.exceptions import (
    ApprovalNotFoundError,
    ApprovalStateTransitionError,
    ApprovalExpiredError,
    ApprovalAlreadyProcessedError,
)


class ApprovalService:
    """Enterprise Human-in-the-Loop approval management service."""

    @staticmethod
    async def create_approval(
        db: AsyncSession,
        organization_id: str,
        requested_by_user_id: str,
        tool_name: str,
        action_type: str,
        action_arguments: dict,
        reason: str,
        conversation_id: Optional[str] = None,
        message_id: Optional[str] = None,
        expires_in_hours: int = 24,
    ) -> Approval:
        """Create a new PENDING approval record strictly scoped to the organization."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expires_in_hours)

        approval = Approval(
            id=str(uuid.uuid4()),
            organization_id=organization_id,
            requested_by_user_id=requested_by_user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            tool_name=tool_name,
            action_type=action_type,
            action_arguments=action_arguments or {},
            reason=reason or f"Request to execute '{tool_name}' ({action_type})",
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
        )

        db.add(approval)
        await db.commit()
        await db.refresh(approval)

        logger.info(
            f"Created approval: id='{approval.id}', tool='{tool_name}', org='{organization_id}', requester='{requested_by_user_id}'"
        )
        return approval

    @staticmethod
    async def get_approval(
        db: AsyncSession,
        approval_id: str,
        organization_id: str,
    ) -> Approval:
        """Fetch an approval by ID ensuring strict organization tenant isolation."""
        res = await db.execute(
            select(Approval).filter(
                Approval.id == approval_id,
                Approval.organization_id == organization_id,
            )
        )
        approval = res.scalar_one_or_none()
        if not approval:
            raise ApprovalNotFoundError(
                f"Approval '{approval_id}' not found in organization '{organization_id}'."
            )

        # Check if pending approval is expired
        if approval.status == ApprovalStatus.PENDING and approval.expires_at:
            if datetime.now(timezone.utc) > approval.expires_at:
                approval.status = ApprovalStatus.EXPIRED
                await db.commit()
                await db.refresh(approval)

        return approval

    @staticmethod
    async def list_approvals(
        db: AsyncSession,
        organization_id: str,
        status: Optional[ApprovalStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Approval], int]:
        """List approvals for an organization with optional status filtering and total count."""
        conditions = [Approval.organization_id == organization_id]
        if status:
            conditions.append(Approval.status == status)

        # Total count query
        count_query = select(func.count(Approval.id)).filter(and_(*conditions))
        total_res = await db.execute(count_query)
        total = total_res.scalar() or 0

        # Items query
        items_query = (
            select(Approval)
            .filter(and_(*conditions))
            .order_by(desc(Approval.created_at))
            .limit(min(limit, 100))
            .offset(offset)
        )
        items_res = await db.execute(items_query)
        approvals = list(items_res.scalars().all())

        return approvals, total

    @staticmethod
    async def approve(
        db: AsyncSession,
        approval_id: str,
        organization_id: str,
        approver_user_id: str,
        approver_role: str,
    ) -> Approval:
        """Approve a pending approval request, enforcing RBAC and anti-self-approval."""
        approval = await ApprovalService.get_approval(db, approval_id, organization_id)

        # 1. State machine transition check
        if approval.status == ApprovalStatus.APPROVED:
            raise ApprovalAlreadyProcessedError(
                f"Approval '{approval_id}' has already been approved."
            )
        if approval.status == ApprovalStatus.EXPIRED:
            raise ApprovalExpiredError(
                f"Approval request '{approval_id}' has expired and cannot be approved."
            )
        if approval.status != ApprovalStatus.PENDING:
            raise ApprovalStateTransitionError(
                f"Cannot approve request with status '{approval.status.value}'. Only PENDING approvals can be approved."
            )

        # 2. Expiration check
        if approval.expires_at and datetime.now(timezone.utc) > approval.expires_at:
            approval.status = ApprovalStatus.EXPIRED
            await db.commit()
            raise ApprovalExpiredError(
                f"Approval '{approval_id}' expired at {approval.expires_at.isoformat()}."
            )

        # 3. RBAC & Anti-Self-Approval enforcement
        ApprovalPermissionChecker.verify_approval_permission(
            user_id=approver_user_id,
            user_role=approver_role,
            requested_by_user_id=approval.requested_by_user_id,
        )

        # 4. Perform transition
        now = datetime.now(timezone.utc)
        approval.status = ApprovalStatus.APPROVED
        approval.approved_by_user_id = approver_user_id
        approval.approved_at = now
        approval.updated_at = now

        await db.commit()
        await db.refresh(approval)

        logger.info(
            f"Approved request: id='{approval.id}', tool='{approval.tool_name}', approver='{approver_user_id}'"
        )
        return approval

    @staticmethod
    async def reject(
        db: AsyncSession,
        approval_id: str,
        organization_id: str,
        rejector_user_id: Optional[str] = None,
        rejector_role: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        approver_user_id: Optional[str] = None,
        approver_role: Optional[str] = None,
    ) -> Approval:
        """Reject a pending approval request, enforcing RBAC and recording rejection reason."""
        user_id = rejector_user_id or approver_user_id
        user_role = rejector_role or approver_role
        if not user_id or not user_role:
            raise ValueError("reject requires reviewer user_id and role")

        approval = await ApprovalService.get_approval(db, approval_id, organization_id)

        # 1. State machine transition check
        if approval.status != ApprovalStatus.PENDING:
            raise ApprovalStateTransitionError(
                f"Cannot reject request with status '{approval.status.value}'. Only PENDING approvals can be rejected."
            )

        # 2. RBAC verification
        ApprovalPermissionChecker.verify_approval_permission(
            user_id=user_id,
            user_role=user_role,
            requested_by_user_id=approval.requested_by_user_id,
        )

        now = datetime.now(timezone.utc)
        approval.status = ApprovalStatus.REJECTED
        approval.approved_by_user_id = user_id  # records reviewer
        approval.approved_at = now
        approval.rejection_reason = rejection_reason or "Rejected by reviewer."
        approval.updated_at = now

        await db.commit()
        await db.refresh(approval)

        logger.info(
            f"Rejected request: id='{approval.id}', tool='{approval.tool_name}', reviewer='{rejector_user_id}'"
        )
        return approval

    @staticmethod
    async def cancel(
        db: AsyncSession,
        approval_id: str,
        organization_id: str,
        user_id: str,
        user_role: str,
    ) -> Approval:
        """Cancel a pending approval request by the requester or management."""
        approval = await ApprovalService.get_approval(db, approval_id, organization_id)

        if approval.status != ApprovalStatus.PENDING:
            raise ApprovalStateTransitionError(
                f"Cannot cancel request with status '{approval.status.value}'. Only PENDING approvals can be cancelled."
            )

        ApprovalPermissionChecker.verify_cancel_permission(
            user_id=user_id,
            user_role=user_role,
            requested_by_user_id=approval.requested_by_user_id,
        )

        now = datetime.now(timezone.utc)
        approval.status = ApprovalStatus.CANCELLED
        approval.updated_at = now

        await db.commit()
        await db.refresh(approval)

        logger.info(f"Cancelled approval: id='{approval.id}', cancelled_by='{user_id}'")
        return approval

    @staticmethod
    async def expire_stale_approvals(
        db: AsyncSession,
        organization_id: Optional[str] = None,
    ) -> int:
        """Transition any PENDING approvals whose expires_at is past now to EXPIRED."""
        now = datetime.now(timezone.utc)
        conditions = [
            Approval.status == ApprovalStatus.PENDING,
            Approval.expires_at <= now,
        ]
        if organization_id:
            conditions.append(Approval.organization_id == organization_id)

        res = await db.execute(select(Approval).filter(and_(*conditions)))
        stale_items = res.scalars().all()
        for item in stale_items:
            item.status = ApprovalStatus.EXPIRED
            item.updated_at = now

        if stale_items:
            await db.commit()
            logger.info(f"Expired {len(stale_items)} stale approval records.")
        return len(stale_items)


approval_service = ApprovalService()
