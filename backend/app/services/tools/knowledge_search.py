import time
from typing import Any, Optional
from pydantic import BaseModel, Field
from app.core.config import settings
from app.core.logging import logger
import app.db.database as db_module
from app.services.retrieval import RetrievalService, ContextBuilder
from app.services.tools.base import BaseTool, ToolContext, ToolResult


class KnowledgeSearchInput(BaseModel):
    """Input payload for internal enterprise knowledge search."""
    query: str = Field(
        ...,
        description="Search query to retrieve relevant enterprise documentation or policies.",
        min_length=1,
        max_length=500,
    )
    top_k: Optional[int] = Field(
        default=None,
        description="Maximum number of relevant document chunks to retrieve (1-10).",
        ge=1,
        le=10,
    )


class KnowledgeSearchOutput(BaseModel):
    """Output payload containing retrieved knowledge chunks and citations."""
    query: str
    chunks_found: int
    sources: list[dict[str, Any]]
    context_str: str


class KnowledgeSearchTool(BaseTool):
    """Searches organization documents and policies using hybrid vector and keyword retrieval."""

    name = "knowledge_search"
    description = "Search internal enterprise documents, uploaded knowledge files, company guidelines, and policies."
    input_schema = KnowledgeSearchInput
    output_schema = KnowledgeSearchOutput
    required_roles = ["MEMBER", "MANAGER", "ADMIN", "OWNER"]

    def __init__(self):
        self.retriever = RetrievalService()
        self.context_builder = ContextBuilder()

    async def execute(self, input_data: KnowledgeSearchInput, context: ToolContext) -> ToolResult:
        start_time = time.time()
        org_id = context.organization_id
        k = input_data.top_k or getattr(settings, "RAG_TOP_K", 5)
        threshold = getattr(settings, "RAG_SIMILARITY_THRESHOLD", 0.3)

        logger.info(
            f"KnowledgeSearchTool: executing hybrid search for org_id='{org_id}', query='{input_data.query[:60]}...'"
        )

        try:
            async with db_module.async_session_maker() as session:
                chunks = await self.retriever.hybrid_search(
                    query=input_data.query,
                    organization_id=org_id,
                    top_k=k,
                    db=session,
                )

            relevant_chunks = [c for c in chunks if c.similarity_score >= threshold]

            if not relevant_chunks:
                elapsed = (time.time() - start_time) * 1000.0
                return ToolResult(
                    success=True,
                    data={
                        "query": input_data.query,
                        "chunks_found": 0,
                        "sources": [],
                        "context_str": "",
                    },
                    execution_time_ms=elapsed,
                )

            context_str, sources = self.context_builder.build_context(relevant_chunks)
            chunks_data = [
                {
                    "document_id": c.document_id,
                    "chunk_id": c.chunk_id,
                    "filename": c.filename,
                    "page": c.page_number,
                    "score": c.similarity_score,
                    "content_snippet": c.content[:200],
                }
                for c in relevant_chunks
            ]
            elapsed = (time.time() - start_time) * 1000.0

            return ToolResult(
                success=True,
                data={
                    "query": input_data.query,
                    "chunks_found": len(relevant_chunks),
                    "chunks": chunks_data,
                    "sources": sources,
                    "context_str": context_str,
                },
                execution_time_ms=elapsed,
            )

        except Exception as e:
            logger.error(f"KnowledgeSearchTool error: {e}", exc_info=True)
            elapsed = (time.time() - start_time) * 1000.0
            return ToolResult(
                success=False,
                error=f"Knowledge retrieval error: {str(e)}",
                execution_time_ms=elapsed,
            )
