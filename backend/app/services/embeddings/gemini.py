import asyncio
from typing import Optional
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logging import logger
from app.services.embeddings.base import EmbeddingProvider


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Google Gemini text embedding provider using the official google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        dimension: Optional[int] = None,
        max_retries: int = 3,
    ):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please set GEMINI_API_KEY in your environment or .env file."
            )
        self.model = model or settings.EMBEDDING_MODEL or "text-embedding-004"
        self._dimension = dimension or settings.VECTOR_DIMENSION or 768
        self.max_retries = max_retries
        self.client = genai.Client(api_key=self.api_key)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def _embed_with_retry(self, contents: list[str]) -> list[list[float]]:
        """Call Gemini embed_content with exponential backoff retry."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                config = types.EmbedContentConfig(output_dimensionality=self._dimension)
                response = await self.client.aio.models.embed_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
                if not response.embeddings:
                    raise RuntimeError("Gemini returned an empty embeddings list.")
                return [e.values for e in response.embeddings]
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Gemini embedding attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        logger.error(f"Gemini embedding failed after {self.max_retries} attempts: {last_exception}")
        raise RuntimeError(f"Gemini embedding service error: {last_exception}") from last_exception

    async def embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for single text string."""
        if not text or not text.strip():
            return [0.0] * self._dimension
        results = await self._embed_with_retry([text])
        return results[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embedding vectors for a list of text strings in configurable batches."""
        if not texts:
            return []

        batch_size = getattr(settings, "EMBEDDING_BATCH_SIZE", 20)
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            # Replace empty strings with a single space to prevent API error
            cleaned_chunk = [t if t and t.strip() else " " for t in chunk]
            embeddings = await self._embed_with_retry(cleaned_chunk)
            all_embeddings.extend(embeddings)

        return all_embeddings
