from pydantic import BaseModel, Field
from typing import Optional


class RAGQueryRequest(BaseModel):
    """Schema for incoming RAG user questions."""
    question: str = Field(..., min_length=1, max_length=2000, description="Question to answer using organization knowledge base")
    top_k: Optional[int] = Field(default=5, ge=1, le=20, description="Maximum number of context chunks to retrieve")


class RAGSource(BaseModel):
    """Citation source metadata for a retrieved document chunk."""
    document_id: str
    chunk_id: str
    filename: str
    page: Optional[int] = None
    chunk_index: int
    score: float


class RAGQueryResponse(BaseModel):
    """Grounded RAG answer response with source citations."""
    answer: str
    sources: list[RAGSource] = []
