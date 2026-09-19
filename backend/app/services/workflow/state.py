from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class WorkflowGraphState(TypedDict, total=False):
    """LangGraph execution state representing a running workflow instance."""
    workflow_id: str
    execution_id: str
    organization_id: str
    user_id: str
    user_role: str
    current_step_index: int
    steps: List[Dict[str, Any]]
    context_data: Dict[str, Any]
    status: str
    error: Optional[str]
    approval_id: Optional[str]
    approval_status: Optional[str]
    pause_for_approval: bool
