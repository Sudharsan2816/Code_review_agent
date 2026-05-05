"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""

    # LLM Provider: "claude" or "openai"
    llm_provider: Literal["claude", "openai"] = "claude"

    # Anthropic / Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "code_review_agent"

    # Human approval gate — set to True to require manual approval before posting
    require_human_approval: bool = False

    # Max diff characters sent to LLM (prevents token overflow)
    max_diff_chars: int = 80_000

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
