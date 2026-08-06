"""Anthropic Claude LLM client with prompt caching."""

import anthropic
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
    "For documentation or repository metadata, report only defects in that file under "
    "code_quality with low/medium severity; prose describing a code risk is not proof "
    "that the risk exists. "
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


class ClaudeClient(BaseLLMClient):
    """Anthropic Claude client using the Messages API with prompt caching."""

    def __init__(self) -> None:
        settings = get_settings()
        self._client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )
        self._model = settings.claude_model

    async def generate_review(self, prompt: str) -> str:
        """Send the diff prompt to Claude and return the raw response text."""
        logger.info(f"Sending review request to Claude model={self._model}")

        message = await self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text
        logger.debug(f"Claude usage: {message.usage}")
        return raw
