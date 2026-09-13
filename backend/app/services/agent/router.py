from app.services.agent.state import AgentState


def decide_retrieval_route(state: AgentState) -> str:
    """Determine whether to route to knowledge retrieval or direct answer generation.
    
    Returns the name of the next node:
    - 'retrieve_knowledge': If the intent requires querying pgvector and organization documents.
    - 'generate_answer': If the intent is conversational or unsupported and does not require retrieval.
    """
    if state.get("needs_retrieval", False):
        return "retrieve_knowledge"
    return "generate_answer"
