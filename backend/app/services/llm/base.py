from abc import ABC, abstractmethod
from typing import Optional, AsyncGenerator


class LLMProvider(ABC):
    """Abstract base class for Large Language Model generation providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        """Generate text completion from prompt with optional system instructions."""
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> AsyncGenerator[str, None]:
        """Yield text token chunks asynchronously as they arrive from the model."""
        pass
