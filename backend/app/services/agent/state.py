from typing import TypedDict, Optional, Any


class AgentState(TypedDict, total=False):
    """Structured, tenant-aware state schema for the LangGraph agent execution."""
    organization_id: str
    user_id: str
    conversation_id: str
    user_message: str
    conversation_history: list[dict[str, str]]
    intent: str  # "knowledge_question" | "conversational" | "unsupported"
    needs_retrieval: bool
    retrieved_context: str
    sources: list[dict[str, Any]]
    final_answer: str
    status: str  # "pending" | "processing" | "completed" | "failed" | "cancelled"
    error: Optional[str]
