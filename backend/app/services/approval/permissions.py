from typing import Optional, Sequence
from app.core.logging import logger
from app.services.approval.exceptions import (
    ApprovalPermissionDeniedError,
    SelfApprovalForbiddenError,
)

APPROVER_ROLES = {"MANAGER", "ADMIN", "OWNER"}
CANCELLER_ROLES = {"MANAGER", "ADMIN", "OWNER"}


class ApprovalPermissionChecker:
    """Enforces role-based authorization and anti-self-approval rules for approvals."""

    @staticmethod
    def can_view(user_role: str) -> bool:
        """Any valid member (including VIEWER) can view organization approval status."""
        return user_role.upper() in {"VIEWER", "MEMBER", "MANAGER", "ADMIN", "OWNER"}

    @staticmethod
    def can_approve(user_role: str) -> bool:
        """Only privileged management roles can approve/reject sensitive actions."""
        return user_role.upper() in APPROVER_ROLES

    @classmethod
    def verify_approval_permission(
        cls,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        requested_by_user_id: Optional[str] = None,
        approver_user_id: Optional[str] = None,
        approver_role: Optional[str] = None,
    ) -> None:
        """Verify that the user is permitted to approve or reject the request."""
        u_id = user_id or approver_user_id
        u_role = user_role or approver_role
        if not u_role or not u_id:
            raise ApprovalPermissionDeniedError("Approver user ID and role are required.")

        # 1. Role verification
        if not cls.can_approve(u_role):
            logger.warning(
                f"Unauthorized approval attempt: user_id='{u_id}', role='{u_role}' lacks approval permissions"
            )
            raise ApprovalPermissionDeniedError(
                f"Role '{u_role}' is not authorized to approve or reject actions. Requires one of {list(APPROVER_ROLES)}."
            )

        # 2. Anti-Self-Approval Enforcement
        if u_id == requested_by_user_id:
            logger.warning(
                f"Self-approval rejected: user_id='{u_id}' attempted to approve their own request"
            )
            raise SelfApprovalForbiddenError(
                "Anti-self-approval policy violation: Requester cannot self-approve their own sensitive action."
            )

    @classmethod
    def verify_cancel_permission(
        cls,
        user_id: str,
        user_role: str,
        requested_by_user_id: str,
    ) -> None:
        """Verify that the user is permitted to cancel the approval request."""
        # Requester can always cancel their own pending request
        if user_id == requested_by_user_id:
            return

        # Managers/Admins/Owners can also cancel pending requests
        if user_role.upper() in CANCELLER_ROLES:
            return

        raise ApprovalPermissionDeniedError(
            f"User '{user_id}' with role '{user_role}' is not authorized to cancel this approval request."
        )
