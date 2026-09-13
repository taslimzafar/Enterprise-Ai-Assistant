import asyncio
from typing import Optional
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.logging import logger
from app.services.llm.base import LLMProvider


class GeminiLLMProvider(LLMProvider):
    """Google Gemini completion provider using the official google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_retries: int = 3,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please set GEMINI_API_KEY in your environment or .env file."
            )
        self.model = model or settings.LLM_MODEL or "gemini-1.5-flash"
        self.max_retries = max_retries
        self.client = genai.Client(api_key=self.api_key)

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
    ) -> str:
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                )
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=config,
                )
                return response.text or ""
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Gemini generate attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        logger.error(f"Gemini LLM generation failed after {self.max_retries} attempts: {last_exception}")
        raise RuntimeError(f"Gemini LLM service error: {last_exception}") from last_exception
