import json
import re
from typing import Any
from app.core.config import settings
from app.core.logging import logger
import app.db.database as db_module
from app.services.agent.state import AgentState
from app.services.agent.prompts import (
    INTENT_CLASSIFIER_SYSTEM,
    CONVERSATIONAL_SYSTEM_INSTRUCTION,
    UNSUPPORTED_SYSTEM_INSTRUCTION,
    format_classifier_prompt,
)
from app.services.llm import get_llm_provider
from app.services.retrieval import RetrievalService, ContextBuilder
from app.services.rag.prompt import RAG_SYSTEM_INSTRUCTION, format_chat_rag_prompt
from app.services.rag.service import NO_ANSWER_FOUND

retriever = RetrievalService()
context_builder = ContextBuilder()

# Fast deterministic regex for common greetings/chitchat
GREETING_PATTERN = re.compile(
    r"^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening)|how\s+are\s+you|thank\s+you|thanks|who\s+are\s+you)\b[!.?]*$",
    re.IGNORECASE,
)


async def load_context_node(state: AgentState) -> dict[str, Any]:
    """Initialize agent execution context and validate parameters."""
    logger.info(
        f"Agent load_context: org_id={state.get('organization_id')}, conv_id={state.get('conversation_id')}"
    )
    return {
        "status": "processing",
        "sources": [],
        "retrieved_context": "",
        "error": None,
    }


async def classify_intent_node(state: AgentState) -> dict[str, Any]:
    """Classify the user's intent into knowledge_question, conversational, or unsupported."""
    query = state.get("user_message", "").strip()

    # Fast path for common greetings without invoking LLM
    if GREETING_PATTERN.match(query):
        logger.info(f"Agent fast-path classified conversational intent: '{query}'")
        return {
            "intent": "conversational",
            "needs_retrieval": False,
        }

    llm = get_llm_provider()
    prompt = format_classifier_prompt(query, state.get("conversation_history"))

    try:
        raw_response = await llm.generate(
            prompt=prompt,
            system_instruction=INTENT_CLASSIFIER_SYSTEM,
            temperature=0.0,
        )

        # Parse JSON from response
        cleaned = raw_response.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        data = json.loads(cleaned)
        intent = data.get("intent", "knowledge_question")
        if intent not in {"knowledge_question", "conversational", "unsupported"}:
            intent = "knowledge_question"

    except Exception as e:
        logger.warning(f"Intent classification failed, defaulting to knowledge_question: {e}")
        intent = "knowledge_question"

    needs_retrieval = intent == "knowledge_question"
    logger.info(f"Agent intent classified: '{intent}', needs_retrieval={needs_retrieval}")
    return {
        "intent": intent,
        "needs_retrieval": needs_retrieval,
    }


async def retrieve_knowledge_node(state: AgentState) -> dict[str, Any]:
    """Perform hybrid search (pgvector + FTS) strictly scoped to the authenticated organization."""
    org_id = state.get("organization_id")
    query = state.get("user_message", "").strip()
    k = getattr(settings, "RAG_TOP_K", 5)
    threshold = getattr(settings, "RAG_SIMILARITY_THRESHOLD", 0.3)

    logger.info(f"Agent retrieve_knowledge: org_id={org_id}, query='{query[:60]}...'")

    async with db_module.async_session_maker() as session:
        retrieved_chunks = await retriever.hybrid_search(
            query=query,
            organization_id=org_id,
            top_k=k,
            db=session,
        )

    relevant_chunks = [c for c in retrieved_chunks if c.similarity_score >= threshold]

    if not relevant_chunks:
        logger.info(f"Agent retrieval yielded 0 chunks above threshold {threshold}")
        return {
            "retrieved_context": "",
            "sources": [],
        }

    context_str, sources = context_builder.build_context(relevant_chunks)
    logger.info(f"Agent retrieval assembled {len(sources)} grounded sources")
    return {
        "retrieved_context": context_str,
        "sources": sources,
    }


async def generate_answer_node(state: AgentState) -> dict[str, Any]:
    """Generate final grounded or conversational answer based on intent and retrieved context."""
    intent = state.get("intent", "knowledge_question")
    query = state.get("user_message", "").strip()
    context_str = state.get("retrieved_context", "")
    llm = get_llm_provider()

    if intent == "conversational":
        answer = await llm.generate(
            prompt=query,
            system_instruction=CONVERSATIONAL_SYSTEM_INSTRUCTION,
            temperature=0.3,
        )
        return {
            "final_answer": answer.strip(),
            "sources": [],
            "status": "completed",
        }

    if intent == "unsupported":
        answer = await llm.generate(
            prompt=query,
            system_instruction=UNSUPPORTED_SYSTEM_INSTRUCTION,
            temperature=0.1,
        )
        return {
            "final_answer": answer.strip(),
            "sources": [],
            "status": "completed",
        }

    # Default knowledge question branch
    if not context_str.strip():
        return {
            "final_answer": NO_ANSWER_FOUND,
            "sources": [],
            "status": "completed",
        }

    prompt = format_chat_rag_prompt(
        question=query,
        context=context_str,
        conversation_history=state.get("conversation_history"),
    )

    answer = await llm.generate(
        prompt=prompt,
        system_instruction=RAG_SYSTEM_INSTRUCTION,
        temperature=0.1,
    )

    cleaned_answer = answer.strip() or NO_ANSWER_FOUND
    return {
        "final_answer": cleaned_answer,
        "status": "completed",
    }
