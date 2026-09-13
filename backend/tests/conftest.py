import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.database import Base
from app.main import app
from app.api.dependencies import get_db
import app.db.database as db_module
from app.db.models import User, Organization, Membership, Document, DocumentChunk

# Target test database in PostgreSQL (enterprise_ai_test) to protect production enterprise_ai data
TEST_DB_URL = settings.DATABASE_URL.replace("/enterprise_ai", "/enterprise_ai_test")

test_engine = create_async_engine(
    TEST_DB_URL,
    echo=False,
    future=True,
    poolclass=NullPool,
)

test_async_session_maker = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

# Bind db_module globals to test engine so health/readiness and direct imports use PostgreSQL test DB
db_module.engine = test_engine
db_module.async_session_maker = test_async_session_maker

async def override_get_db():
    async with test_async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

app.dependency_overrides[get_db] = override_get_db


from sqlalchemy import text
import hashlib
import math
from app.services.embeddings.base import EmbeddingProvider
from app.services.llm.base import LLMProvider
import app.services.embeddings as emb_module
import app.services.llm as llm_module


class TestEmbeddingProvider(EmbeddingProvider):
    """Deterministic offline embedding provider for test execution."""
    def __init__(self, dimension: int = 768):
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_text(self, text: str) -> list[float]:
        # Hash text to create a deterministic vector
        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [float(b) / 255.0 for b in h]
        full_vec = (raw * (self._dim // len(raw) + 1))[:self._dim]
        norm = math.sqrt(sum(x * x for x in full_vec)) or 1.0
        return [round(x / norm, 5) for x in full_vec]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed_text(t) for t in texts]


class TestLLMProvider(LLMProvider):
    """Deterministic LLM completion provider for test execution."""
    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        if "refund" in prompt.lower():
            return "Our refund policy allows full refunds within 30 days of purchase [Source: test_verify.txt]."
        if "unrelated" in prompt.lower() or "secret" in prompt.lower():
            return "I couldn't find this information in the organization's knowledge base."
        return "Based on the organization documentation, the requested information is verified [Source: test_verify.txt]."

    async def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
    ):
        full_text = await self.generate(prompt, system_instruction, temperature)
        words = full_text.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.005)


# Bind test providers
emb_module._embedding_provider_instance = TestEmbeddingProvider()
llm_module._llm_provider_instance = TestLLMProvider()


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture(scope="session")
def event_loop(request):
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
