"""PostgreSQL infrastructure: async engine plumbing.

Repository adapters receive a ``sqlalchemy.ext.asyncio.AsyncEngine`` built from
``Settings.database_url`` (asyncpg driver). Nothing in the domain/application layers
imports this package; only the composition root (adapters and dependency providers) does,
so swapping the engine/pool strategy is a change confined to this module.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.infrastructure.config.settings import get_settings

__all__ = ["create_async_engine_from_url", "get_async_engine"]


def create_async_engine_from_url(database_url: str) -> AsyncEngine:
    """Build an async SQLAlchemy engine bound to ``database_url``.

    No connection is opened here; SQLAlchemy connects lazily on first use.
    """

    return create_async_engine(database_url)


@lru_cache
def get_async_engine() -> AsyncEngine:
    """Return the process-wide async engine bound to ``Settings.database_url``.

    Cached so the app's default repository shares one connection pool.
    """

    return create_async_engine_from_url(get_settings().database_url)
