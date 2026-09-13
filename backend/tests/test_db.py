import pytest
import asyncio
from sqlalchemy import text
from app.db.database import engine, async_session_maker
from app.db.models.user import User
import uuid

async def test_db_connection():
    """Test that we can connect to the database and execute a simple query."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1

async def test_db_crud():
    """Test basic CRUD operations on a model."""
    test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    
    async with async_session_maker() as session:
        # Create
        new_user = User(
            email=test_email,
            hashed_password="fakehash",
            is_active=True,
            is_superuser=False
        )
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        
        assert new_user.id is not None
        assert new_user.email == test_email
        
        # Read
        from sqlalchemy import select
        stmt = select(User).where(User.email == test_email)
        result = await session.execute(stmt)
        fetched_user = result.scalar_one_or_none()
        
        assert fetched_user is not None
        assert fetched_user.id == new_user.id
        
        # Cleanup
        await session.delete(fetched_user)
        await session.commit()
