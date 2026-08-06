"""NVIDIA NIM client using its OpenAI-compatible chat endpoint."""

from openai import AsyncOpenAI
from loguru import logger

from app.config import get_settings
from app.services.llm.base import BaseLLMClient
from app.services.llm.openai_client import _SYSTEM_PROMPT


class NvidiaClient(BaseLLMClient):
    """Generate structured reviews through NVIDIA's hosted NIM API."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(
            api_key=settings.nvidia_api_key,
            base_url=settings.nvidia_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
        self._model = settings.nvidia_model

    async def generate_review(self, prompt: str) -> str:
        logger.info(f"Sending review request to NVIDIA model={self._model}")
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
