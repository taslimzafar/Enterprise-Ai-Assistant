from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, RoleChecker
from app.db.models.membership import Membership, RoleEnum
from app.schemas.rag import RAGQueryRequest, RAGQueryResponse
from app.services.rag import RAGService
from app.core.logging import logger

from app.core.rate_limit import rate_limiter
from app.core.config import settings

router = APIRouter()
rag_service = RAGService()


@router.post("/query", response_model=RAGQueryResponse)
async def query_knowledge_base(
    payload: RAGQueryRequest,
    org_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    membership: Membership = Depends(
        RoleChecker([RoleEnum.OWNER, RoleEnum.ADMIN, RoleEnum.MANAGER, RoleEnum.MEMBER])
    ),
):
    """Query the enterprise knowledge base using RAG.
    
    Authenticates user, verifies active organization membership and RBAC role,
    and returns a grounded answer with citations scoped strictly to the organization.
    """
    # Rate limit RAG queries
    await rate_limiter.check(
        f"rag:{membership.organization_id}:{membership.user_id}",
        limit=settings.RATE_LIMIT_AI_PER_MINUTE,
    )

    cleaned_q = payload.question.strip()
    if not cleaned_q:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty or whitespace.",
        )

    try:
        result = await rag_service.query(
            question=cleaned_q,
            organization_id=membership.organization_id,
            top_k=payload.top_k,
            db=db,
        )
        return result
    except Exception as e:
        logger.error(f"RAG query execution error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your query. Please try again later.",
        )
