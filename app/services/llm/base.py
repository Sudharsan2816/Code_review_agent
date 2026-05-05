"""Abstract base class for LLM clients."""

import json
import re
from abc import ABC, abstractmethod

from app.models.review import CodeReview


class BaseLLMClient(ABC):
    """Contract that every LLM backend must fulfil."""

    @abstractmethod
    async def generate_review(self, prompt: str) -> str:
        """Send prompt to the LLM and return the raw text response."""

    async def parse_review_response(self, raw: str) -> dict:
        """
        Extract JSON from a raw LLM response.

        The LLM is instructed to wrap its JSON inside ```json … ``` fences.
        Falls back to scanning for the first '{' … '}' block.
        """
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if fenced:
            return json.loads(fenced.group(1))

        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(raw[start:end])

        raise ValueError(f"No JSON object found in LLM response:\n{raw[:500]}")
