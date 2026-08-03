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

    # LLM Provider: "claude", "openai", or NVIDIA's OpenAI-compatible API
    llm_provider: Literal["claude", "openai", "nvidia"] = "claude"

    # Anthropic / Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # NVIDIA NIM
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "nvidia/llama-3.3-nemotron-super-49b-v1"

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
    api_auth_token: str = ""
    cors_allowed_origins: str = "http://localhost:8000"
    debug: bool = False

    @property
    def cors_origins(self) -> list[str]:
        """Return the explicitly configured browser origins."""
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ] or ["http://localhost:8000"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
