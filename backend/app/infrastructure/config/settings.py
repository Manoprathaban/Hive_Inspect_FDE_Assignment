"""Application settings, loaded from the environment.

Backed by Pydantic Settings so values arrive typed. Secrets never live in code; provide
them via environment variables or ``backend/.env`` (git-ignored). Never commit real values.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "get_settings", "get_cors_origins"]


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Hive Inspect Template Importer"
    app_env: str = "development"
    debug: bool = False

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hive_inspect"

    gemini_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


def get_cors_origins() -> list[str]:
    """Split :attr:`Settings.cors_origins` into a list of origin strings."""
    return [origin.strip() for origin in get_settings().cors_origins.split(",") if origin.strip()]