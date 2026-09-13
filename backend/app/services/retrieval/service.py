from dataclasses import dataclass, field
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pgvector.sqlalchemy import Vector

from app.core.config import settings
from app.core.logging import logger
from app.services.embeddings import get_embedding_provider


@dataclass
class RetrievalResult:
    """Structured result item from vector or hybrid retrieval."""
    document_id: str
    chunk_id: str
    content: str
    similarity_score: float
    filename: str
    page_number: Optional[int] = None
    chunk_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class RetrievalService:
    """Service for semantic vector search, full-text keyword search, and hybrid fusion.
    
    All searches strictly enforce organization_id isolation.
    """

    def __init__(self):
        self.vector_weight = getattr(settings, "HYBRID_VECTOR_WEIGHT", 0.7)
        self.keyword_weight = getattr(settings, "HYBRID_KEYWORD_WEIGHT", 0.3)
        self.rrf_k = getattr(settings, "RRF_K", 60)

    async def vector_search(
        self,
        query_vector: list[float],
        organization_id: str,
        top_k: int,
        db: AsyncSession,
    ) -> list[RetrievalResult]:
        """Perform semantic similarity search using pgvector cosine distance <=>."""
        vector_str = f"[{','.join(str(x) for x in query_vector)}]"
        stmt = text("""
            SELECT 
                dc.id AS chunk_id,
                dc.document_id,
                dc.chunk_index,
                dc.content,
                dc.page_number,
                d.original_filename,
                1 - (dc.embedding <=> CAST(:query_vector AS vector)) AS similarity
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE dc.organization_id = :org_id
              AND dc.embedding IS NOT NULL
            ORDER BY dc.embedding <=> CAST(:query_vector AS vector) ASC
            LIMIT :top_k
        """)

        result = await db.execute(
            stmt,
            {"query_vector": vector_str, "org_id": organization_id, "top_k": top_k},
        )
        rows = result.fetchall()

        return [
            RetrievalResult(
                document_id=r.document_id,
                chunk_id=r.chunk_id,
                content=r.content,
                similarity_score=float(r.similarity) if r.similarity is not None else 0.0,
                filename=r.original_filename,
                page_number=r.page_number,
                chunk_index=r.chunk_index,
                metadata={"source": "vector"},
            )
            for r in rows
        ]

    async def keyword_search(
        self,
        query_text: str,
        organization_id: str,
        top_k: int,
        db: AsyncSession,
    ) -> list[RetrievalResult]:
        """Perform PostgreSQL full-text keyword search using plainto_tsquery."""
        cleaned_query = query_text.strip()
        if not cleaned_query:
            return []

        stmt = text("""
            SELECT 
                dc.id AS chunk_id,
                dc.document_id,
                dc.chunk_index,
                dc.content,
                dc.page_number,
                d.original_filename,
                ts_rank(to_tsvector('english', dc.content), plainto_tsquery('english', :query)) AS rank
            FROM document_chunks dc
            JOIN documents d ON d.id = dc.document_id
            WHERE dc.organization_id = :org_id
              AND to_tsvector('english', dc.content) @@ plainto_tsquery('english', :query)
            ORDER BY rank DESC
            LIMIT :top_k
        """)

        result = await db.execute(
            stmt,
            {"query": cleaned_query, "org_id": organization_id, "top_k": top_k},
        )
        rows = result.fetchall()

        return [
            RetrievalResult(
                document_id=r.document_id,
                chunk_id=r.chunk_id,
                content=r.content,
                similarity_score=float(r.rank) if r.rank is not None else 0.0,
                filename=r.original_filename,
                page_number=r.page_number,
                chunk_index=r.chunk_index,
                metadata={"source": "keyword"},
            )
            for r in rows
        ]

    async def hybrid_search(
        self,
        query: str,
        organization_id: str,
        top_k: int,
        db: AsyncSession,
    ) -> list[RetrievalResult]:
        """Execute hybrid search combining vector similarity and keyword search via Reciprocal Rank Fusion (RRF)."""
        fetch_k = max(top_k * 2, 10)

        # 1. Generate query embedding vector
        embedder = get_embedding_provider()
        query_vector = await embedder.embed_text(query)

        # 2. Execute parallel/sequential retrievals
        vector_results = await self.vector_search(query_vector, organization_id, fetch_k, db)
        keyword_results = await self.keyword_search(query, organization_id, fetch_k, db)

        # 3. Reciprocal Rank Fusion (RRF)
        # score = sum(weight * (1 / (k + rank)))
        scores: dict[str, float] = {}
        items: dict[str, RetrievalResult] = {}

        for rank, res in enumerate(vector_results, start=1):
            chunk_id = res.chunk_id
            items[chunk_id] = res
            scores[chunk_id] = scores.get(chunk_id, 0.0) + self.vector_weight * (1.0 / (self.rrf_k + rank))

        for rank, res in enumerate(keyword_results, start=1):
            chunk_id = res.chunk_id
            if chunk_id not in items:
                items[chunk_id] = res
            scores[chunk_id] = scores.get(chunk_id, 0.0) + self.keyword_weight * (1.0 / (self.rrf_k + rank))

        if not items:
            return []

        # Sort items by computed RRF score descending
        sorted_ids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
        max_score = max(scores.values()) if scores else 1.0

        fused_results: list[RetrievalResult] = []
        for cid in sorted_ids[:top_k]:
            item = items[cid]
            norm_score = scores[cid] / max_score if max_score > 0 else 0.0
            item.similarity_score = round(norm_score, 4)
            item.metadata["rrf_score"] = scores[cid]
            fused_results.append(item)

        logger.info(
            f"Hybrid retrieval completed: org_id={organization_id}, "
            f"vector_hits={len(vector_results)}, keyword_hits={len(keyword_results)}, "
            f"fused_results={len(fused_results)}"
        )
        return fused_results
