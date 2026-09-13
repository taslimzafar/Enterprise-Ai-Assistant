import json
import asyncio
from typing import AsyncGenerator, Optional
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
import app.db.database as db_module
from app.db.models.conversation import Conversation
from app.db.models.message import Message, MessageRole, MessageStatus
from app.services.retrieval import RetrievalService, ContextBuilder
from app.services.llm import get_llm_provider
from app.services.rag.prompt import RAG_SYSTEM_INSTRUCTION, format_chat_rag_prompt
from app.services.rag.service import NO_ANSWER_FOUND


class ChatService:
    """Service handling multi-tenant conversations, message history, and real-time SSE streaming."""

    def __init__(self):
        self.retriever = RetrievalService()
        self.context_builder = ContextBuilder()

    async def create_conversation(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
        title: Optional[str] = None,
    ) -> Conversation:
        """Create a new conversation scoped strictly to an organization and user."""
        conversation = Conversation(
            organization_id=organization_id,
            user_id=user_id,
            title=title or "New Conversation",
        )
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
        return conversation

    async def list_conversations(
        self,
        db: AsyncSession,
        organization_id: str,
        user_id: str,
        limit: int = 50,
    ) -> list[Conversation]:
        """List conversations for a user within an organization ordered by most recent."""
        result = await db.execute(
            select(Conversation)
            .filter(
                Conversation.organization_id == organization_id,
                Conversation.user_id == user_id,
            )
            .order_by(desc(Conversation.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_conversation(
        self,
        db: AsyncSession,
        conversation_id: str,
        organization_id: str,
    ) -> Optional[Conversation]:
        """Retrieve a conversation ensuring organization tenant isolation."""
        result = await db.execute(
            select(Conversation).filter(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_conversation_title(
        self,
        db: AsyncSession,
        conversation_id: str,
        organization_id: str,
        title: str,
    ) -> Optional[Conversation]:
        """Update the title of an existing conversation."""
        conversation = await self.get_conversation(db, conversation_id, organization_id)
        if not conversation:
            return None
        conversation.title = title.strip()[:255]
        await db.commit()
        await db.refresh(conversation)
        return conversation

    async def delete_conversation(
        self,
        db: AsyncSession,
        conversation_id: str,
        organization_id: str,
    ) -> bool:
        """Delete a conversation and all its cascade-associated messages."""
        conversation = await self.get_conversation(db, conversation_id, organization_id)
        if not conversation:
            return False
        await db.delete(conversation)
        await db.commit()
        return True

    async def get_messages(
        self,
        db: AsyncSession,
        conversation_id: str,
        organization_id: str,
        limit: int = 100,
    ) -> list[Message]:
        """Fetch chronologically ordered messages for a validated conversation."""
        conversation = await self.get_conversation(db, conversation_id, organization_id)
        if not conversation:
            return []
        result = await db.execute(
            select(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def stream_chat_response(
        self,
        conversation_id: str,
        user_text: str,
        organization_id: str,
        user_id: str,
    ) -> AsyncGenerator[str, None]:
        """Execute RAG retrieval and stream SSE response tokens with cancellation support."""
        cleaned_query = user_text.strip()
        if not cleaned_query:
            yield f"event: error\ndata: {json.dumps({'error': 'Message content cannot be empty.'})}\n\n"
            return

        assistant_msg_id: Optional[str] = None
        accumulated_text = ""
        sources: list[dict] = []

        try:
            # 1. Open session to validate conversation & persist user message
            async with db_module.async_session_maker() as session:
                conversation = await self.get_conversation(session, conversation_id, organization_id)
                if not conversation:
                    yield f"event: error\ndata: {json.dumps({'error': 'Conversation not found or access denied.'})}\n\n"
                    return

                # Save user message
                user_msg = Message(
                    conversation_id=conversation_id,
                    role=MessageRole.USER,
                    content=cleaned_query,
                    status=MessageStatus.COMPLETED,
                )
                session.add(user_msg)

                # Auto-title if untitled or "New Conversation"
                if not conversation.title or conversation.title == "New Conversation":
                    derived = cleaned_query[:40].strip()
                    if len(cleaned_query) > 40:
                        derived += "..."
                    conversation.title = derived

                await session.commit()
                current_title = conversation.title

                # Fetch past conversation messages (last 6 messages for prompt history)
                history_query = await session.execute(
                    select(Message)
                    .filter(
                        Message.conversation_id == conversation_id,
                        Message.id != user_msg.id,
                        Message.status == MessageStatus.COMPLETED,
                    )
                    .order_by(desc(Message.created_at))
                    .limit(6)
                )
                past_messages = list(reversed(history_query.scalars().all()))
                formatted_history = [
                    {"role": m.role.value, "content": m.content}
                    for m in past_messages
                ]

                # Create pending assistant message placeholder
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    role=MessageRole.ASSISTANT,
                    content="",
                    status=MessageStatus.STREAMING,
                )
                session.add(assistant_msg)
                await session.commit()
                await session.refresh(assistant_msg)
                assistant_msg_id = assistant_msg.id

            # 2. Emit start event
            yield f"event: message_start\ndata: {json.dumps({'message_id': assistant_msg_id, 'conversation_id': conversation_id, 'title': current_title})}\n\n"

            # 3. Delegate execution to LangGraph AgentService
            from app.services.agent import agent_service

            agent_stream = agent_service.stream_chat(
                organization_id=organization_id,
                user_id=user_id,
                conversation_id=conversation_id,
                message=cleaned_query,
                conversation_history=formatted_history,
            )

            agent_meta = {
                "agent": {
                    "version": "v1",
                    "intent": "knowledge_question",
                    "retrieval_used": True,
                    "sources_count": 0,
                },
                "sources": [],
            }

            async for item in agent_stream:
                ev_type = item.get("event")
                ev_data = item.get("data", {})

                if ev_type == "agent_intent":
                    agent_meta["agent"]["intent"] = ev_data.get("intent", "knowledge_question")
                    agent_meta["agent"]["retrieval_used"] = ev_data.get("needs_retrieval", False)
                    yield f"event: agent_intent\ndata: {json.dumps(ev_data)}\n\n"

                elif ev_type == "citation":
                    sources = ev_data.get("sources", [])
                    agent_meta["sources"] = sources
                    agent_meta["agent"]["sources_count"] = len(sources)
                    yield f"event: citation\ndata: {json.dumps(ev_data)}\n\n"

                elif ev_type == "token":
                    token_text = ev_data.get("text", "")
                    accumulated_text += token_text
                    yield f"event: token\ndata: {json.dumps(ev_data)}\n\n"

                elif ev_type == "agent_complete":
                    agent_meta["agent"]["sources_count"] = ev_data.get("sources_count", len(sources))
                    agent_meta["sources"] = ev_data.get("sources", sources)

            # 4. Finalize assistant message in DB with agent execution metadata
            final_content = accumulated_text.strip() or NO_ANSWER_FOUND
            async with db_module.async_session_maker() as session:
                res = await session.execute(select(Message).filter(Message.id == assistant_msg_id))
                msg = res.scalar_one_or_none()
                if msg:
                    msg.content = final_content
                    msg.status = MessageStatus.COMPLETED
                    msg.msg_metadata = agent_meta
                    await session.commit()

            yield f"event: message_complete\ndata: {json.dumps({'message_id': assistant_msg_id, 'status': 'completed'})}\n\n"

        except asyncio.CancelledError:
            # Client disconnected or cancelled stream
            logger.warning(f"Chat stream cancelled by client: msg_id={assistant_msg_id}")
            if assistant_msg_id:
                try:
                    async with db_module.async_session_maker() as session:
                        res = await session.execute(select(Message).filter(Message.id == assistant_msg_id))
                        msg = res.scalar_one_or_none()
                        if msg:
                            msg.content = accumulated_text or "(Generation stopped)"
                            msg.status = MessageStatus.CANCELLED
                            msg.msg_metadata = {"sources": sources, "cancelled": True}
                            await session.commit()
                except Exception as save_err:
                    logger.error(f"Failed to record cancelled message state: {save_err}")
            raise

        except Exception as e:
            logger.error(f"Error in chat stream generation: {e}", exc_info=True)
            if assistant_msg_id:
                try:
                    async with db_module.async_session_maker() as session:
                        res = await session.execute(select(Message).filter(Message.id == assistant_msg_id))
                        msg = res.scalar_one_or_none()
                        if msg:
                            msg.status = MessageStatus.FAILED
                            msg.msg_metadata = {"error": "Generation failed."}
                            await session.commit()
                except Exception as fail_err:
                    logger.error(f"Failed to record failed message state: {fail_err}")

            yield f"event: error\ndata: {json.dumps({'error': 'An error occurred while generating the assistant response.'})}\n\n"
