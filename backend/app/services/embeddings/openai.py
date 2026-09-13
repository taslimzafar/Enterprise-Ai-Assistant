import asyncio
from typing import Optional
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import logger
from app.services.embeddings.base import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI text embedding provider using AsyncOpenAI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dimension: Optional[int] = None,
        max_retries: int = 3,
    ):
        self.api_key = api_key if api_key is not None else settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Please set OPENAI_API_KEY in your environment or .env file."
            )
        self.model = model or "text-embedding-3-small"
        self._dimension = dimension or settings.VECTOR_DIMENSION or 1536
        self.max_retries = max_retries
        self.client = AsyncOpenAI(api_key=self.api_key)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=texts,
                    dimensions=self._dimension if "text-embedding-3" in self.model else None,
                )
                return [d.embedding for d in response.data]
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"OpenAI embedding attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        logger.error(f"OpenAI embedding failed after {self.max_retries} attempts: {last_exception}")
        raise RuntimeError(f"OpenAI embedding service error: {last_exception}") from last_exception

    async def embed_text(self, text: str) -> list[float]:
        if not text or not text.strip():
            return [0.0] * self._dimension
        results = await self._embed_with_retry([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        batch_size = getattr(settings, "EMBEDDING_BATCH_SIZE", 20)
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            cleaned_chunk = [t if t and t.strip() else " " for t in chunk]
            embeddings = await self._embed_with_retry(cleaned_chunk)
            all_embeddings.extend(embeddings)

        return all_embeddings
