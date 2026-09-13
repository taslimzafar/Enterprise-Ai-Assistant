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
    TOOL_DECISION_SYSTEM,
    TOOL_ANSWER_SYSTEM_INSTRUCTION,
    format_classifier_prompt,
    format_tool_decision_prompt,
    format_tool_answer_prompt,
)
from app.services.llm import get_llm_provider
from app.services.retrieval import RetrievalService, ContextBuilder
from app.services.rag.prompt import RAG_SYSTEM_INSTRUCTION, format_chat_rag_prompt
from app.services.rag.service import NO_ANSWER_FOUND
from app.services.tools import tool_registry, ToolContext, ToolResult

retriever = RetrievalService()
context_builder = ContextBuilder()

# Fast deterministic regex for common greetings/chitchat
GREETING_PATTERN = re.compile(
    r"^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening)|how\s+are\s+you|thank\s+you|thanks|who\s+are\s+you)\b[!.?]*$",
    re.IGNORECASE,
)

# Fast deterministic regex for calculation requests
CALC_PATTERN = re.compile(
    r"^(?:calculate|compute|what\s+is|evaluate)?\s*([\d\.\s\+\-\*\/\%\(\)\^]+)$",
    re.IGNORECASE,
)


async def load_context_node(state: AgentState) -> dict[str, Any]:
    """Initialize agent execution context and validate parameters."""
    logger.info(
        f"Agent load_context: org_id={state.get('organization_id')}, conv_id={state.get('conversation_id')}, role={state.get('user_role', 'MEMBER')}"
    )
    return {
        "status": "processing",
        "sources": state.get("sources", []),
        "retrieved_context": state.get("retrieved_context", ""),
        "selected_tool": None,
        "tool_arguments": None,
        "tool_result": None,
        "tool_error": None,
        "tool_call_count": state.get("tool_call_count", 0),
        "tool_history": state.get("tool_history", []),
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


async def agent_decision_node(state: AgentState) -> dict[str, Any]:
    """Analyze query and available tools to decide whether to call a tool or direct answer."""
    intent = state.get("intent", "knowledge_question")
    query = state.get("user_message", "").strip()
    user_role = state.get("user_role", "MEMBER")

    if intent in {"conversational", "unsupported"}:
        return {
            "selected_tool": None,
            "tool_arguments": None,
        }

    # 1. Fast path: check for simple arithmetic calculations
    calc_match = CALC_PATTERN.match(query)
    # Ensure there's at least one digit and one operator or percentage
    if calc_match and any(c.isdigit() for c in query) and any(op in query for op in "+-*/%^"):
        expr = calc_match.group(1).strip()
        logger.info(f"Fast-path detected calculator tool: '{expr}'")
        return {
            "selected_tool": "calculator",
            "tool_arguments": {"expression": expr},
        }

    # 2. Fast path: check for document metadata or database stats queries
    lower_query = query.lower()
    if (
        "how many documents" in lower_query
        or "count documents" in lower_query
        or "total documents" in lower_query
    ):
        return {
            "selected_tool": "database_query",
            "tool_arguments": {"operation": "count_documents"},
        }
    if (
        "organization statistics" in lower_query
        or "org statistics" in lower_query
        or "organization stats" in lower_query
    ):
        return {
            "selected_tool": "database_query",
            "tool_arguments": {"operation": "organization_statistics"},
        }
    if "count conversations" in lower_query or "total conversations" in lower_query:
        return {
            "selected_tool": "database_query",
            "tool_arguments": {"operation": "count_conversations"},
        }

    # 3. LLM-based tool decision
    available_tools = tool_registry.get_tool_definitions(user_role)
    llm = get_llm_provider()
    prompt = format_tool_decision_prompt(
        question=query,
        available_tools=available_tools,
        history=state.get("conversation_history"),
    )

    try:
        raw_response = await llm.generate(
            prompt=prompt,
            system_instruction=TOOL_DECISION_SYSTEM,
            temperature=0.0,
        )
        cleaned = raw_response.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()

        data = json.loads(cleaned)
        action = data.get("action")
        if action == "call_tool":
            tool_name = data.get("tool")
            args = data.get("arguments", {})
            return {
                "selected_tool": tool_name,
                "tool_arguments": args,
            }
    except Exception as e:
        logger.warning(f"Tool decision reasoning failed, defaulting to knowledge_search: {e}")

    # Default knowledge question branch to knowledge_search tool
    return {
        "selected_tool": "knowledge_search",
        "tool_arguments": {"query": query},
    }


async def execute_tool_node(state: AgentState) -> dict[str, Any]:
    """Safely execute the selected tool with strict context boundaries and call limits."""
    tool_name = state.get("selected_tool")
    tool_args = state.get("tool_arguments") or {}
    tool_call_count = state.get("tool_call_count", 0)
    max_calls = getattr(settings, "AGENT_MAX_TOOL_CALLS", 5)

    if not tool_name:
        return {}

    # Strict limit check
    if tool_call_count >= max_calls:
        logger.warning(f"Max tool calls ({max_calls}) reached. Rejecting call to '{tool_name}'")
        return {
            "tool_error": f"Tool call limit reached ({max_calls} maximum calls permitted per request).",
            "selected_tool": None,
        }

    # Build authenticated ToolContext
    context = ToolContext(
        organization_id=state.get("organization_id", ""),
        user_id=state.get("user_id", ""),
        user_role=state.get("user_role", "MEMBER"),
        conversation_id=state.get("conversation_id"),
    )

    logger.info(
        f"Executing tool '{tool_name}' (call {tool_call_count + 1}/{max_calls}) for org='{context.organization_id}'"
    )

    result: ToolResult = await tool_registry.execute_tool(
        tool_name=tool_name,
        arguments=tool_args,
        context=context,
    )

    updated_history = list(state.get("tool_history", []))
    updated_history.append({
        "tool": tool_name,
        "success": result.success,
        "execution_time_ms": result.execution_time_ms,
        "arguments": tool_args,
    })

    updates: dict[str, Any] = {
        "tool_call_count": tool_call_count + 1,
        "tool_history": updated_history,
        "selected_tool": None,  # Reset selected tool
    }

    if result.success:
        updates["tool_result"] = result.data
        updates["tool_error"] = None

        # If knowledge_search, also populate sources and retrieved_context for seamless citations
        if tool_name == "knowledge_search" and isinstance(result.data, dict):
            updates["sources"] = result.data.get("sources", [])
            updates["retrieved_context"] = result.data.get("context_str", "")
    else:
        updates["tool_result"] = None
        updates["tool_error"] = result.error

    return updates


async def retrieve_knowledge_node(state: AgentState) -> dict[str, Any]:
    """Direct hybrid search (pgvector + FTS) for Phase 8 backward compatibility."""
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
    """Generate final grounded, conversational, or tool-synthesized answer."""
    intent = state.get("intent", "knowledge_question")
    query = state.get("user_message", "").strip()
    context_str = state.get("retrieved_context", "")
    tool_history = state.get("tool_history", [])
    tool_result = state.get("tool_result")
    tool_error = state.get("tool_error")
    llm = get_llm_provider()

    # 1. Conversational intent
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

    # 2. Unsupported intent
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

    # 3. If tools were executed
    if tool_history:
        last_tool = tool_history[-1]["tool"]

        # If knowledge search was executed, preserve grounded citation formatting
        if last_tool == "knowledge_search":
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
            return {
                "final_answer": answer.strip() or NO_ANSWER_FOUND,
                "status": "completed",
            }

        # For calculator or database_query or tool error
        prompt = format_tool_answer_prompt(
            question=query,
            tool_name=last_tool,
            tool_arguments=tool_history[-1].get("arguments"),
            tool_result=tool_result,
            tool_error=tool_error,
        )
        answer = await llm.generate(
            prompt=prompt,
            system_instruction=TOOL_ANSWER_SYSTEM_INSTRUCTION,
            temperature=0.1,
        )
        return {
            "final_answer": answer.strip(),
            "status": "completed",
        }

    # 4. Fallback for knowledge questions without tool history
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
    return {
        "final_answer": answer.strip() or NO_ANSWER_FOUND,
        "status": "completed",
    }
