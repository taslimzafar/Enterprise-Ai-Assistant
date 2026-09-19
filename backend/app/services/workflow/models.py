from dataclasses import dataclass, field
from typing import Any, Optional, Dict
from app.db.models.workflow import (
    WorkflowStatus,
    ExecutionStatus,
    StepExecutionStatus,
    StepType,
)


@dataclass
class StepResult:
    """Standardized result of a single workflow step execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    requires_approval: bool = False
    approval_id: Optional[str] = None
    approval_data: Optional[Dict[str, Any]] = None
    skipped: bool = False


@dataclass
class WorkflowExecutionContext:
    """Runtime context passed across workflow steps."""
    workflow_id: str
    execution_id: str
    organization_id: str
    user_id: str
    user_role: str
    data: Dict[str, Any] = field(default_factory=dict)
