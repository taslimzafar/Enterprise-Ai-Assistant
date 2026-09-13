from app.core.config import settings
from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.gemini import GeminiEmbeddingProvider
from app.services.embeddings.openai import OpenAIEmbeddingProvider

_embedding_provider_instance: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Factory function returning the configured EmbeddingProvider singleton.
    
    Supports provider switching via EMBEDDING_PROVIDER ('gemini' or 'openai')
    without altering retrieval or storage layers.
    """
    global _embedding_provider_instance
    if _embedding_provider_instance is None:
        provider_type = (settings.EMBEDDING_PROVIDER or "gemini").lower()
        if provider_type == "gemini":
            _embedding_provider_instance = GeminiEmbeddingProvider()
        elif provider_type == "openai":
            _embedding_provider_instance = OpenAIEmbeddingProvider()
        else:
            raise ValueError(f"Unsupported EMBEDDING_PROVIDER: '{provider_type}'")
    return _embedding_provider_instance


def reset_embedding_provider() -> None:
    """Reset the singleton instance (useful for testing)."""
    global _embedding_provider_instance
    _embedding_provider_instance = None
