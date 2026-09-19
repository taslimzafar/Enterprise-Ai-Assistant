class WorkflowError(Exception):
    """Base exception for all workflow-related errors."""
    pass


class WorkflowNotFoundError(WorkflowError):
    """Raised when a workflow cannot be found."""
    pass


class WorkflowExecutionNotFoundError(WorkflowError):
    """Raised when a workflow execution cannot be found."""
    pass


class WorkflowValidationError(WorkflowError):
    """Raised when a workflow definition or step configuration is invalid."""
    pass


class WorkflowStateError(WorkflowError):
    """Raised when an illegal operation is attempted given the workflow/execution state."""
    pass


class InvalidStateTransitionError(WorkflowStateError):
    """Raised when an invalid state transition is attempted on a workflow or execution."""
    pass


class InvalidConditionError(WorkflowValidationError):
    """Raised when a conditional branch expression is malformed or invalid."""
    pass


class StepExecutionError(WorkflowError):
    """Raised when an error occurs during step execution."""
    pass


class ApprovalRequiredPause(WorkflowError):
    """Special signal exception raised to pause workflow for human approval."""
    def __init__(self, approval_id: str, tool_name: str, step_id: str, message: str = "Workflow paused for human approval."):
        super().__init__(message)
        self.approval_id = approval_id
        self.tool_name = tool_name
        self.step_id = step_id


class CrossTenantAccessError(WorkflowError):
    """Raised when attempting to access or modify workflows across tenant boundaries."""
    pass


class WorkflowPermissionDeniedError(WorkflowError):
    """Raised when an unauthorized user attempts an operation on workflows."""
    pass
