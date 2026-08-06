"""OpenAI GPT LLM client."""

from openai import AsyncOpenAI
from loguru import logger

from app.config import get_settings
from app.services.llm.base import BaseLLMClient

_SYSTEM_PROMPT = (
    "You are an expert software engineer performing a thorough code review. "
    "You will be given a git diff of a pull request. "
    "Review ONLY added or deleted lines present in that diff. Never infer issues "
    "from referenced files, repository context, or unchanged code. Every finding "
    "must name an exact changed file and include one exact changed line as evidence "
    "without the leading diff marker. If no changed line supports a finding, omit it. "
    "Documentation-only changes must not produce findings about application code. "
    "Respond ONLY with a single valid JSON object — no prose before or after. "
    "Use this exact schema:\n"
    "{\n"
    '  "bugs": [{"file": "...", "line": <int|null>, "evidence": "exact changed line", "description": "...", "severity": "low|medium|high|critical"}],\n'
    '  "security": [{"file": "...", "line": <int|null>, "evidence": "exact changed line", "description": "...", "severity": "..."}],\n'
    '  "performance": [{"file": "...", "line": <int|null>, "evidence": "exact changed line", "description": "...", "severity": "..."}],\n'
    '  "code_quality": [{"file": "...", "line": <int|null>, "evidence": "exact changed line", "description": "...", "severity": "..."}],\n'
    '  "suggested_fixes": [{"file": "...", "issue": "...", "original": "...", "improved": "...", "explanation": "..."}],\n'
    '  "scores": {"quality": <1-10>, "security": <1-10>, "performance": <1-10>},\n'
    '  "final_verdict": "APPROVE|REQUEST_CHANGES|COMMENT",\n'
    '  "summary": "..."\n'
    "}"
)


class OpenAIClient(BaseLLMClient):
    """OpenAI client using the Chat Completions API with JSON mode."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    async def generate_review(self, prompt: str) -> str:
        """Send the diff prompt to OpenAI and return the raw response text."""
        logger.info(f"Sending review request to OpenAI model={self._model}")

        response = await self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4096,
            temperature=0.2,
        )

        raw = response.choices[0].message.content or ""
        logger.debug(f"OpenAI usage: {response.usage}")
        return raw
