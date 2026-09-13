from typing import Sequence
from app.core.config import settings
from app.services.retrieval.service import RetrievalResult


class ContextBuilder:
    """Assembles retrieved document chunks into structured context for the LLM prompt.
    
    Enforces configurable character and token limits to prevent context overflow.
    """

    def __init__(self, max_chars: int | None = None):
        self.max_chars = max_chars or getattr(settings, "RAG_CONTEXT_CHAR_LIMIT", 8000)

    def build_context(self, chunks: Sequence[RetrievalResult]) -> tuple[str, list[dict]]:
        """Build structured context string and citation source list from retrieval results.
        
        Returns:
            context_str: Formatted context blocks with metadata markers.
            sources: Cleaned list of citation metadata dictionaries.
        """
        if not chunks:
            return "", []

        context_blocks: list[str] = []
        sources: list[dict] = []
        total_chars = 0

        for i, chunk in enumerate(chunks, start=1):
            page_str = f", Page {chunk.page_number}" if chunk.page_number is not None else ""
            header = f"[Document: {chunk.filename}{page_str}, Chunk: {chunk.chunk_index}, DocID: {chunk.document_id}]"
            block = f"{header}\n{chunk.content}\n"

            # Check character limit budget
            if total_chars + len(block) > self.max_chars and context_blocks:
                break

            context_blocks.append(block)
            total_chars += len(block)

            sources.append({
                "document_id": chunk.document_id,
                "chunk_id": chunk.chunk_id,
                "filename": chunk.filename,
                "page": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "score": chunk.similarity_score,
            })

        context_str = "\n---\n".join(context_blocks)
        return context_str, sources
