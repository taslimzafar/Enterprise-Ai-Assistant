import asyncio
from typing import Optional
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import logger
from app.services.llm.base import LLMProvider


class OpenAILLMProvider(LLMProvider):
    """OpenAI completion provider using AsyncOpenAI."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 3,
    ):
        self.api_key = api_key or settings.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Please set OPENAI_API_KEY in your environment or .env file."
            )
        self.model = model or getattr(settings, "LLM_MODEL", "gpt-4o-mini")
        self.max_retries = max_retries
        self.client = AsyncOpenAI(api_key=self.api_key)

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"OpenAI generate attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        logger.error(f"OpenAI LLM generation failed after {self.max_retries} attempts: {last_exception}")
        raise RuntimeError(f"OpenAI LLM service error: {last_exception}") from last_exception

    async def generate_stream(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ):
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"OpenAI streaming generation failed: {e}")
            raise RuntimeError(f"OpenAI streaming error: {e}") from e
