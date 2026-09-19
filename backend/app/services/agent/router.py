from app.services.agent.state import AgentState


def decide_retrieval_route(state: AgentState) -> str:
    """Legacy route for Phase 8 compatibility."""
    if state.get("needs_retrieval", False) or state.get("selected_tool"):
        return "retrieve_knowledge"
    return "generate_answer"


def decide_tool_route(state: AgentState) -> str:
    """Route based on whether a tool was selected during agent decision."""
    if state.get("selected_tool"):
        return "execute_tool"
    return "generate_answer"


def decide_execution_route(state: AgentState) -> str:
    """Consolidated router directing to approval check, tool execution, legacy retrieval, or direct answer."""
    if state.get("selected_tool"):
        return "approval_check"
    if state.get("needs_retrieval", False):
        return "retrieve_knowledge"
    return "generate_answer"


def decide_approval_route(state: AgentState) -> str:
    """Route after approval check: if approved and tool still set, proceed to execute_tool; else generate_answer."""
    if state.get("selected_tool") and not state.get("approval_required"):
        return "execute_tool"
    return "generate_answer"
