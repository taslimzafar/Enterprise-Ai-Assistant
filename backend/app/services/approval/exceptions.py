class ApprovalError(Exception):
    """Base exception for all approval-related errors."""
    pass


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval record cannot be found."""
    pass


class CrossTenantAccessError(ApprovalError):
    """Raised when an approval record is accessed or modified across tenant boundaries."""
    pass


class ApprovalStateTransitionError(ApprovalError):
    """Raised when an invalid state transition is attempted on an approval."""
    pass


InvalidStateTransitionError = ApprovalStateTransitionError


class ApprovalPermissionDeniedError(ApprovalError):
    """Raised when an unauthorized user attempts to approve, reject, or modify an approval."""
    pass


class ApprovalExpiredError(ApprovalError):
    """Raised when attempting to approve or execute an expired approval."""
    pass


class SelfApprovalForbiddenError(ApprovalError):
    """Raised when the requesting user attempts to approve their own sensitive action."""
    pass


class ApprovalTamperingError(ApprovalError):
    """Raised when an approval payload has been altered, forged, or mismatched."""
    pass


class ApprovalAlreadyProcessedError(ApprovalStateTransitionError):
    """Raised when an action has already been executed or approved (replay prevention)."""
    pass
