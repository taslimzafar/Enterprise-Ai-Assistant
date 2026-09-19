from typing import TypedDict, Optional, Any


class AgentState(TypedDict, total=False):
    """Structured, tenant-aware state schema for the LangGraph agent execution."""
    organization_id: str
    user_id: str
    user_role: str
    conversation_id: str
    user_message: str
    conversation_history: list[dict[str, str]]
    intent: str  # "knowledge_question" | "conversational" | "unsupported" | "tool_required"
    needs_retrieval: bool
    retrieved_context: str
    sources: list[dict[str, Any]]
    final_answer: str
    status: str  # "pending" | "processing" | "completed" | "failed" | "cancelled"
    error: Optional[str]
    # Phase 9: Controlled Tool Calling state
    selected_tool: Optional[str]
    tool_arguments: Optional[dict[str, Any]]
    tool_result: Optional[dict[str, Any]]
    tool_error: Optional[str]
    tool_call_count: int
    tool_history: list[dict[str, Any]]
    # Phase 10: Human-in-the-Loop approval state
    approval_required: bool
    approval_id: Optional[str]
    approval_status: Optional[str]
    approval_data: Optional[dict[str, Any]]
