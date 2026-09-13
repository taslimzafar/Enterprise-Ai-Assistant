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

            # 3. Retrieve relevant chunks from Phase 6 knowledge base
            async with db_module.async_session_maker() as session:
                k = getattr(settings, "RAG_TOP_K", 5)
                retrieved_chunks = await self.retriever.hybrid_search(
                    query=cleaned_query,
                    organization_id=organization_id,
                    top_k=k,
                    db=session,
                )

            threshold = getattr(settings, "RAG_SIMILARITY_THRESHOLD", 0.3)
            relevant_chunks = [c for c in retrieved_chunks if c.similarity_score >= threshold]

            # 4. Fallback if no relevant knowledge found
            if not relevant_chunks:
                logger.info(f"Stream RAG query yielded no chunks above {threshold} for org_id={organization_id}")
                yield f"event: citation\ndata: {json.dumps({'sources': []})}\n\n"
                
                # Stream fallback text
                for word in NO_ANSWER_FOUND.split(" "):
                    accumulated_text += word + " "
                    yield f"event: token\ndata: {json.dumps({'text': word + ' '})}\n\n"
                    await asyncio.sleep(0.02)

                # Finalize message in DB
                async with db_module.async_session_maker() as session:
                    res = await session.execute(select(Message).filter(Message.id == assistant_msg_id))
                    msg = res.scalar_one_or_none()
                    if msg:
                        msg.content = NO_ANSWER_FOUND
                        msg.status = MessageStatus.COMPLETED
                        msg.msg_metadata = {"sources": []}
                        await session.commit()

                yield f"event: message_complete\ndata: {json.dumps({'message_id': assistant_msg_id, 'status': 'completed'})}\n\n"
                return

            # 5. Build context & emit citations
            context_str, sources = self.context_builder.build_context(relevant_chunks)
            yield f"event: citation\ndata: {json.dumps({'sources': sources})}\n\n"

            # 6. Stream tokens from LLM Provider
            prompt = format_chat_rag_prompt(
                question=cleaned_query,
                context=context_str,
                conversation_history=formatted_history,
            )
            llm = get_llm_provider()

            token_stream = llm.generate_stream(
                prompt=prompt,
                system_instruction=RAG_SYSTEM_INSTRUCTION,
                temperature=0.1,
            )

            async for token in token_stream:
                accumulated_text += token
                yield f"event: token\ndata: {json.dumps({'text': token})}\n\n"

            # 7. Finalize assistant message in DB
            final_content = accumulated_text.strip() or NO_ANSWER_FOUND
            async with db_module.async_session_maker() as session:
                res = await session.execute(select(Message).filter(Message.id == assistant_msg_id))
                msg = res.scalar_one_or_none()
                if msg:
                    msg.content = final_content
                    msg.status = MessageStatus.COMPLETED
                    msg.msg_metadata = {"sources": sources}
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
