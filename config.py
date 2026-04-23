"""Centralised runtime configuration.

Uses :class:`pydantic_settings.BaseSettings` so values come from environment
variables (and, in development, a local ``.env`` file via ``python-dotenv``).
No secrets are read from files in production; Cloud Run injects them from
Secret Manager.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    All fields are typed; unknown env vars are ignored to avoid surprising
    overrides. Sensitive values (e.g. ``GROQ_API_KEY``) are never logged.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="loan-risk-multiagent")
    environment: str = Field(default="production")
    port: int = Field(default=8080, ge=1, le=65535)

    groq_api_key: str | None = Field(default=None)
    groq_model: str = Field(default="llama-3.3-70b-versatile")
    groq_timeout_seconds: float = Field(default=30.0, gt=0)
    groq_max_retries: int = Field(default=2, ge=0, le=5)

    database_url: str = Field(default="sqlite:////tmp/apilog.db")

    cors_allowed_origins: str = Field(default="*")
    rate_limit_default: str = Field(default="60/minute")
    rate_limit_assess: str = Field(default="30/minute")
    rate_limit_storage_uri: str = Field(default="memory://")

    log_level: str = Field(default="INFO")

    @property
    def allowed_origins_list(self) -> list[str]:
        raw = (self.cors_allowed_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()
