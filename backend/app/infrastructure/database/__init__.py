"""PostgreSQL infrastructure: async engine plumbing and RLS request scoping.

Repository adapters receive a ``sqlalchemy.ext.asyncio.AsyncEngine`` built from
``Settings.database_url`` (asyncpg driver). Nothing in the domain/application layers
imports this package; only the composition root (adapters and dependency providers) does,
so swapping the engine/pool strategy is a change confined to this module.

:func:`owner_scoped_connection` is the other half of that plumbing. RLS policies keyed on
``auth.uid()`` (``database/migrations/0002_rls_policies.sql``) cannot bind to a connection
that owns the tables, so every request runs its transaction as the non-owner role created
by ``0003_rls_enforcement.sql`` and publishes the acting user's claims. See
``docs/DATABASE_DESIGN.md`` §6.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.infrastructure.config.settings import get_settings

__all__ = [
    "apply_rls_context",
    "create_async_engine_from_url",
    "get_async_engine",
    "owner_scoped_connection",
]

# A role name reaches SQL through SET ROLE, which takes no bind parameters, so it is
# validated against a strict identifier pattern and quoted rather than interpolated raw.
_ROLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_role(app_role: str) -> str:
    """Return ``app_role`` as a quoted SQL identifier, rejecting anything unsafe."""

    if not _ROLE_NAME_PATTERN.match(app_role):
        raise ValueError(f"Refusing to SET ROLE to an invalid role name: {app_role!r}")
    return f'"{app_role}"'


async def apply_rls_context(conn: AsyncConnection, *, owner_id: uuid.UUID, app_role: str) -> None:
    """Assume the non-owner app role and publish the acting user's JWT claims.

    Must run inside an already-open transaction. ``SET LOCAL`` and ``set_config(..., true)``
    are both transaction-scoped, so the identity is discarded on COMMIT/ROLLBACK and a
    pooled connection can never leak one user's identity into the next user's request.

    ``owner_id`` comes from the verified ``UserContext``; the request body never supplies it.
    """

    await conn.execute(text(f"SET LOCAL ROLE {_quote_role(app_role)}"))
    claims = json.dumps({"sub": str(owner_id), "role": "authenticated"})
    await conn.execute(
        text("SELECT set_config('request.jwt.claims', CAST(:claims AS text), true)"),
        {"claims": claims},
    )
    # Supabase's auth.uid() reads `request.jwt.claim.sub` in some versions and
    # `request.jwt.claims` in others, so both are set and either definition resolves.
    await conn.execute(
        text("SELECT set_config('request.jwt.claim.sub', CAST(:sub AS text), true)"),
        {"sub": str(owner_id)},
    )


@asynccontextmanager
async def owner_scoped_connection(
    engine: AsyncEngine, *, owner_id: uuid.UUID, app_role: str
) -> AsyncIterator[AsyncConnection]:
    """Yield a connection in a transaction scoped to ``owner_id`` under ``app_role``.

    Yields an open ``AsyncConnection`` with the transaction already begun and the RLS
    context applied, so statements issued on it are filtered by the 0002 policies. The
    transaction commits when the block exits normally and rolls back on any exception.
    """

    async with engine.connect() as conn:
        async with conn.begin():
            await apply_rls_context(conn, owner_id=owner_id, app_role=app_role)
            yield conn


def create_async_engine_from_url(database_url: str) -> AsyncEngine:
    """Build an async SQLAlchemy engine bound to ``database_url``.

    No connection is opened here; SQLAlchemy connects lazily on first use.

    The pool is deliberately wider than SQLAlchemy's default of 5. Reading one template
    issues its child-table queries concurrently (see
    ``app/adapters/repositories/postgres.py::_load_template``), so a single request can hold
    several connections at once; on the default pool that turned into connection churn
    against a remote pooler, where every new connection pays a TLS handshake. ``pool_timeout``
    is raised so a burst degrades into waiting for a pooled connection rather than erroring.
    """

    return create_async_engine(
        database_url,
        pool_size=10,
        max_overflow=10,
        pool_timeout=30,
    )


@lru_cache
def get_async_engine() -> AsyncEngine:
    """Return the process-wide async engine bound to ``Settings.database_url``.

    Cached so the app's default repository shares one connection pool.
    """

    return create_async_engine_from_url(get_settings().database_url)
