from langgraph.graph import StateGraph, START, END
from app.services.agent.state import AgentState
from app.services.agent.nodes import (
    load_context_node,
    classify_intent_node,
    retrieve_knowledge_node,
    generate_answer_node,
)
from app.services.agent.router import decide_retrieval_route


def create_agent_graph():
    """Build and compile the deterministic LangGraph enterprise agent workflow.
    
    Graph topology:
    START
      ↓
    load_context
      ↓
    classify_intent
      ↓
    [decide_retrieval_route]
      ├── retrieve_knowledge → generate_answer → END
      └── generate_answer ─────────────────────→ END
    """
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("load_context", load_context_node)
    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("retrieve_knowledge", retrieve_knowledge_node)
    workflow.add_node("generate_answer", generate_answer_node)

    # Add linear start edges
    workflow.add_edge(START, "load_context")
    workflow.add_edge("load_context", "classify_intent")

    # Add conditional branching edge
    workflow.add_conditional_edges(
        "classify_intent",
        decide_retrieval_route,
        {
            "retrieve_knowledge": "retrieve_knowledge",
            "generate_answer": "generate_answer",
        },
    )

    # Connect to termination
    workflow.add_edge("retrieve_knowledge", "generate_answer")
    workflow.add_edge("generate_answer", END)

    return workflow.compile()
