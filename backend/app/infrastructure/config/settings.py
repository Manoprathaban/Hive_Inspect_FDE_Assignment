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

    # Browser origins allowed to call the API. The defaults are the frontend's own dev
    # server (5173), its production-build preview (4173) and the alternate dev port (3000);
    # a deployed frontend origin must be set explicitly via the environment.
    cors_origins: str = "http://localhost:5173,http://localhost:4173,http://localhost:3000"

    max_upload_bytes: int = 10 * 1024 * 1024

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hive_inspect"

    # Non-owner PostgreSQL role that request transactions assume (SET LOCAL ROLE) so the
    # auth.uid()-keyed RLS policies from 0002 bind instead of being bypassed by the table
    # owner; the acting user's claims are published alongside it. Created by
    # database/migrations/0003_rls_enforcement.sql. Set empty to disable, which is only
    # correct where 0002 is a no-op (plain PostgreSQL with no `auth` schema) and the
    # application layer's owner_id predicates are the sole enforcement point.
    db_app_role: str = "hive_app"

    # Supabase Auth (production). SUPABASE_JWT_SECRET signs the access tokens the API
    # validates; it is required whenever APP_ENV=production (the provider fails closed).
    supabase_jwt_secret: str | None = None
    supabase_url: str | None = None

    gemini_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


def get_cors_origins() -> list[str]:
    """Split :attr:`Settings.cors_origins` into a list of origin strings."""
    return [origin.strip() for origin in get_settings().cors_origins.split(",") if origin.strip()]
