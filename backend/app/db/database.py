from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logging import logger

from sqlalchemy.engine import make_url

logger.info(f"Connecting to database at {make_url(settings.DATABASE_URL).render_as_string(hide_password=True)}")

import sys
from sqlalchemy.pool import NullPool

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "development",
    future=True,
    poolclass=NullPool if "pytest" in sys.modules else None,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# Declarative base for models
class Base(DeclarativeBase):
    pass
