RAG_SYSTEM_INSTRUCTION = """You are an enterprise knowledge assistant.
Your job is to answer employee questions strictly and truthfully using the provided context from organization documents.

RULES:
1. Ground your answer completely in the provided context. Do NOT invent or assume facts not explicitly stated in the context.
2. If the context does not contain sufficient information to answer the question, state clearly: "I couldn't find this information in the organization's knowledge base." Do NOT attempt to answer from outside knowledge.
3. Explicitly cite your sources using the document filename and page number where available, for example: [Source: Handbook.pdf, Page 4].
4. Maintain strict professional tone and organizational privacy.
5. If different documents contain conflicting information, highlight the discrepancy with citations.
"""

def format_rag_prompt(question: str, context: str) -> str:
    """Format the grounded RAG user prompt combining context and user query."""
    return f"""CONTEXT FROM ORGANIZATION DOCUMENTS:
{context}

USER QUESTION:
{question}

Please provide a grounded, factual answer based solely on the context above, citing sources where appropriate:"""


def format_chat_rag_prompt(
    question: str,
    context: str,
    conversation_history: list[dict] | None = None,
) -> str:
    """Format the grounded RAG user prompt combining document context, recent chat history, and current question."""
    history_str = ""
    if conversation_history:
        formatted_history = []
        for msg in conversation_history:
            role_label = "User" if msg.get("role") == "user" else "Assistant"
            content = msg.get("content", "").strip()
            if content:
                formatted_history.append(f"{role_label}: {content}")
        if formatted_history:
            history_str = "RECENT CONVERSATION HISTORY:\n" + "\n".join(formatted_history) + "\n\n"

    return f"""CONTEXT FROM ORGANIZATION DOCUMENTS:
{context}

{history_str}USER QUESTION:
{question}

Please provide a grounded, factual answer based solely on the context above, citing sources where appropriate:"""
