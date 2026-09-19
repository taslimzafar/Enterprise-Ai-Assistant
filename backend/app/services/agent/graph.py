from langgraph.graph import StateGraph, START, END
from app.services.agent.state import AgentState
from app.services.agent.nodes import (
    load_context_node,
    classify_intent_node,
    agent_decision_node,
    approval_check_node,
    execute_tool_node,
    retrieve_knowledge_node,
    generate_answer_node,
)
from app.services.agent.router import decide_execution_route, decide_approval_route


def create_agent_graph():
    """Build and compile the Phase 10 LangGraph enterprise agent workflow with HITL approvals.

    Graph topology:
    START
      ↓
    load_context
      ↓
    classify_intent
      ↓
    agent_decision
      ↓
    [decide_execution_route]
      ├── approval_check ──────► [decide_approval_route]
      │                            ├── execute_tool ──► generate_answer → END
      │                            └── generate_answer ─────────────────→ END
      ├── retrieve_knowledge ──► generate_answer → END
      └── generate_answer ───────────────────────────→ END
    """
    workflow = StateGraph(AgentState)

    # Add all workflow nodes
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("agent_decision", agent_decision_node)
    workflow.add_node("approval_check", approval_check_node)
    workflow.add_node("execute_tool", execute_tool_node)
    workflow.add_node("retrieve_knowledge", retrieve_knowledge_node)
    workflow.add_node("generate_answer", generate_answer_node)

    # Start edges
    workflow.add_edge(START, "load_context")
    workflow.add_edge("load_context", "classify_intent")
    workflow.add_edge("classify_intent", "agent_decision")

    # Conditional branching from agent_decision
    workflow.add_conditional_edges(
        "agent_decision",
        decide_execution_route,
        {
            "approval_check": "approval_check",
            "retrieve_knowledge": "retrieve_knowledge",
            "generate_answer": "generate_answer",
        },
    )

    # Conditional branching from approval_check
    workflow.add_conditional_edges(
        "approval_check",
        decide_approval_route,
        {
            "execute_tool": "execute_tool",
            "generate_answer": "generate_answer",
        },
    )

    # Reconvergence to generate_answer and END
    workflow.add_edge("execute_tool", "generate_answer")
    workflow.add_edge("retrieve_knowledge", "generate_answer")
    workflow.add_edge("generate_answer", END)

    return workflow.compile()
