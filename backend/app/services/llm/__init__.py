from app.core.config import settings
from app.services.llm.base import LLMProvider
from app.services.llm.gemini import GeminiLLMProvider
from app.services.llm.openai import OpenAILLMProvider

_llm_provider_instance: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """Factory function returning the configured LLMProvider singleton."""
    global _llm_provider_instance
    if _llm_provider_instance is None:
        provider_type = (settings.LLM_PROVIDER or "gemini").lower()
        if provider_type == "gemini":
            _llm_provider_instance = GeminiLLMProvider()
        elif provider_type == "openai":
            _llm_provider_instance = OpenAILLMProvider()
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: '{provider_type}'")
    return _llm_provider_instance


def reset_llm_provider() -> None:
    """Reset the singleton instance (useful for testing)."""
    global _llm_provider_instance
    _llm_provider_instance = None
