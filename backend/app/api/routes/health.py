from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()

@router.get("/health")
async def health_check():
    """
    Check if the API is running and healthy.
    """
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }

@router.get("/ready")
async def readiness_check():
    """
    Check if the API is ready to accept traffic.
    Will be extended later to check DB and external dependencies.
    """
    # TODO: Add database connection check here
    return {
        "status": "ready"
    }
