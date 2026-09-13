import asyncio
from typing import AsyncGenerator, Any, Optional
from app.core.logging import logger
from app.services.agent.graph import create_agent_graph
from app.services.agent.state import AgentState
from app.services.agent.nodes import (
    classify_intent_node,
    agent_decision_node,
    execute_tool_node,
    retrieve_knowledge_node,
)
from app.services.agent.prompts import (
    CONVERSATIONAL_SYSTEM_INSTRUCTION,
    UNSUPPORTED_SYSTEM_INSTRUCTION,
    TOOL_ANSWER_SYSTEM_INSTRUCTION,
    format_tool_answer_prompt,
)
from app.services.llm import get_llm_provider
from app.services.rag.prompt import RAG_SYSTEM_INSTRUCTION, format_chat_rag_prompt
from app.services.rag.service import NO_ANSWER_FOUND


class AgentService:
    """Orchestration service wrapping the compiled LangGraph enterprise agent."""

    def __init__(self):
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            self._graph = create_agent_graph()
        return self._graph

    async def run(
        self,
        organization_id: str,
        user_id: str,
        conversation_id: str,
        message: str,
        conversation_history: list[dict[str, str]] | None = None,
        user_role: str = "MEMBER",
    ) -> AgentState:
        """Run the full LangGraph agent synchronously to completion."""
        initial_state: AgentState = {
            "organization_id": organization_id,
            "user_id": user_id,
            "user_role": user_role,
            "conversation_id": conversation_id,
            "user_message": message.strip(),
            "conversation_history": conversation_history or [],
            "sources": [],
            "status": "pending",
            "tool_call_count": 0,
            "tool_history": [],
        }

        final_state = await self.graph.ainvoke(initial_state)
        return final_state

    async def stream_chat(
        self,
        organization_id: str,
        user_id: str,
        conversation_id: str,
        message: str,
        conversation_history: list[dict[str, str]] | None = None,
        user_role: str = "MEMBER",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute the agent workflow and stream structured lifecycle events, tool executions, and tokens."""
        query = message.strip()
        history = conversation_history or []

        state: AgentState = {
            "organization_id": organization_id,
            "user_id": user_id,
            "user_role": user_role,
            "conversation_id": conversation_id,
            "user_message": query,
            "conversation_history": history,
            "sources": [],
            "status": "processing",
            "tool_call_count": 0,
            "tool_history": [],
        }

        yield {"event": "agent_start", "data": {"agent_version": "v1"}}

        # 1. Classify Intent Node
        intent_update = await classify_intent_node(state)
        state.update(intent_update)
        intent = state.get("intent", "knowledge_question")
        needs_retrieval = state.get("needs_retrieval", False)

        yield {
            "event": "agent_intent",
            "data": {
                "intent": intent,
                "needs_retrieval": needs_retrieval,
            },
        }

        # 2. Agent Decision Node (Determine if a tool is needed)
        decision_update = await agent_decision_node(state)
        state.update(decision_update)
        selected_tool = state.get("selected_tool")

        # 3. Tool Execution (if tool selected)
        if selected_tool:
            yield {"event": "tool_start", "data": {"tool": selected_tool}}

            tool_exec_update = await execute_tool_node(state)
            state.update(tool_exec_update)

            # Check if knowledge search returned sources
            sources = state.get("sources", [])
            if sources:
                yield {"event": "citation", "data": {"sources": sources}}

            if state.get("tool_error"):
                yield {
                    "event": "tool_error",
                    "data": {"tool": selected_tool, "error": state.get("tool_error")},
                }
            else:
                yield {
                    "event": "tool_complete",
                    "data": {"tool": selected_tool, "success": True},
                }
        elif needs_retrieval:
            # Fallback legacy retrieval route
            yield {"event": "retrieval_start", "data": {}}
            retrieval_update = await retrieve_knowledge_node(state)
            state.update(retrieval_update)
            sources = state.get("sources", [])
            yield {"event": "citation", "data": {"sources": sources}}
            yield {"event": "retrieval_complete", "data": {"sources_count": len(sources)}}

        sources = state.get("sources", [])
        retrieved_context = state.get("retrieved_context", "")
        tool_history = state.get("tool_history", [])
        tool_result = state.get("tool_result")
        tool_error = state.get("tool_error")

        # 4. Generation Node (Streaming tokens)
        yield {"event": "generation_start", "data": {}}
        accumulated_text = ""
        llm = get_llm_provider()

        if intent == "conversational":
            token_stream = llm.generate_stream(
                prompt=query,
                system_instruction=CONVERSATIONAL_SYSTEM_INSTRUCTION,
                temperature=0.3,
            )
            async for token in token_stream:
                accumulated_text += token
                yield {"event": "token", "data": {"text": token}}

        elif intent == "unsupported":
            token_stream = llm.generate_stream(
                prompt=query,
                system_instruction=UNSUPPORTED_SYSTEM_INSTRUCTION,
                temperature=0.1,
            )
            async for token in token_stream:
                accumulated_text += token
                yield {"event": "token", "data": {"text": token}}

        elif tool_history:
            last_tool = tool_history[-1]["tool"]
            if last_tool == "knowledge_search":
                if not retrieved_context.strip():
                    for word in NO_ANSWER_FOUND.split(" "):
                        accumulated_text += word + " "
                        yield {"event": "token", "data": {"text": word + " "}}
                        await asyncio.sleep(0.015)
                else:
                    prompt = format_chat_rag_prompt(
                        question=query,
                        context=retrieved_context,
                        conversation_history=history,
                    )
                    token_stream = llm.generate_stream(
                        prompt=prompt,
                        system_instruction=RAG_SYSTEM_INSTRUCTION,
                        temperature=0.1,
                    )
                    async for token in token_stream:
                        accumulated_text += token
                        yield {"event": "token", "data": {"text": token}}
            else:
                prompt = format_tool_answer_prompt(
                    question=query,
                    tool_name=last_tool,
                    tool_arguments=tool_history[-1].get("arguments"),
                    tool_result=tool_result,
                    tool_error=tool_error,
                )
                token_stream = llm.generate_stream(
                    prompt=prompt,
                    system_instruction=TOOL_ANSWER_SYSTEM_INSTRUCTION,
                    temperature=0.1,
                )
                async for token in token_stream:
                    accumulated_text += token
                    yield {"event": "token", "data": {"text": token}}

        else:
            # Knowledge question fallback
            if not retrieved_context.strip():
                for word in NO_ANSWER_FOUND.split(" "):
                    accumulated_text += word + " "
                    yield {"event": "token", "data": {"text": word + " "}}
                    await asyncio.sleep(0.015)
            else:
                prompt = format_chat_rag_prompt(
                    question=query,
                    context=retrieved_context,
                    conversation_history=history,
                )
                token_stream = llm.generate_stream(
                    prompt=prompt,
                    system_instruction=RAG_SYSTEM_INSTRUCTION,
                    temperature=0.1,
                )
                async for token in token_stream:
                    accumulated_text += token
                    yield {"event": "token", "data": {"text": token}}

        final_answer = accumulated_text.strip() or NO_ANSWER_FOUND

        yield {
            "event": "agent_complete",
            "data": {
                "agent_version": "v1",
                "intent": intent,
                "retrieval_used": needs_retrieval or bool(sources),
                "sources_count": len(sources),
                "final_answer": final_answer,
                "sources": sources,
                "tool_history": tool_history,
            },
        }
