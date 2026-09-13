from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.services.retrieval import RetrievalService, ContextBuilder
from app.services.llm import get_llm_provider
from app.services.rag.prompt import RAG_SYSTEM_INSTRUCTION, format_rag_prompt

NO_ANSWER_FOUND = "I couldn't find this information in the organization's knowledge base."


class RAGService:
    """Orchestrates the complete Retrieval-Augmented Generation (RAG) pipeline:
    
    Question → Hybrid Retrieval → Context Assembly → LLM Grounded Answer → Citations.
    """

    def __init__(self):
        self.retriever = RetrievalService()
        self.context_builder = ContextBuilder()

    async def query(
        self,
        question: str,
        organization_id: str,
        top_k: int | None = None,
        db: AsyncSession | None = None,
    ) -> dict:
        """Process a user query against the organization's indexed knowledge base."""
        cleaned_question = question.strip()
        if not cleaned_question:
            return {
                "answer": "Please provide a valid, non-empty question.",
                "sources": [],
            }

        k = top_k or getattr(settings, "RAG_TOP_K", 5)

        logger.info(f"RAG query started: org_id={organization_id}, question='{cleaned_question[:80]}...'")

        # 1. Hybrid search across organization's document chunks
        retrieved_chunks = await self.retriever.hybrid_search(
            query=cleaned_question,
            organization_id=organization_id,
            top_k=k,
            db=db,
        )

        # 2. Check for empty or low relevance results
        threshold = getattr(settings, "RAG_SIMILARITY_THRESHOLD", 0.3)
        relevant_chunks = [c for c in retrieved_chunks if c.similarity_score >= threshold]

        if not relevant_chunks:
            logger.info(f"RAG query yielded no relevant chunks above threshold {threshold}: org_id={organization_id}")
            return {
                "answer": NO_ANSWER_FOUND,
                "sources": [],
            }

        # 3. Assemble structured context
        context_str, sources = self.context_builder.build_context(relevant_chunks)

        if not context_str.strip():
            return {
                "answer": NO_ANSWER_FOUND,
                "sources": [],
            }

        # 4. Generate grounded completion from LLM
        prompt = format_rag_prompt(question=cleaned_question, context=context_str)
        llm = get_llm_provider()

        try:
            answer = await llm.generate(
                prompt=prompt,
                system_instruction=RAG_SYSTEM_INSTRUCTION,
                temperature=0.1,
            )
        except Exception as e:
            logger.error(f"LLM generation failed in RAG service: {e}")
            raise RuntimeError(f"Error generating answer from AI service: {e}") from e

        # Fallback check if model itself reported lack of information
        cleaned_answer = answer.strip()
        if not cleaned_answer:
            cleaned_answer = NO_ANSWER_FOUND

        logger.info(
            f"RAG query successfully completed: org_id={organization_id}, "
            f"sources_count={len(sources)}, answer_length={len(cleaned_answer)}"
        )

        return {
            "answer": cleaned_answer,
            "sources": sources,
        }
