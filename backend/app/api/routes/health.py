from fastapi import APIRouter, status, HTTPException
from sqlalchemy import text
from app.core.config import settings
from app.db.database import engine
from app.core.logging import logger

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
    Includes a database connection check.
    """
    db_status = "ok"
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database readiness check failed: {e}")
        db_status = "error"
        
    if db_status == "error":
        # In a real setup, we might return 503 Service Unavailable if DB is down
        # but returning JSON with error state is also common.
        pass
        
    return {
        "status": "ready" if db_status == "ok" else "not_ready",
        "database": db_status
    }
