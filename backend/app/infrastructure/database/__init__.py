"""Database / persistence wiring.

Edge infrastructure only — never imported by application/domain code. Engine creation is
lazy so the app boots without a live database. Supabase is only the managed PostgreSQL
hosting layer; we talk to it via PostgreSQL (SQLAlchemy async + asyncpg).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.infrastructure.config.settings import get_settings

__all__ = ["create_engine"]


def create_engine() -> AsyncEngine:
    """Create an async SQLAlchemy engine from the configured ``DATABASE_URL``."""
    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)