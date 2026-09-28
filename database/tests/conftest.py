"""Live-database test harness for the Hive Inspect migrations.

Every test runs against a real PostgreSQL server (local, Supabase-compatible, or CI).
Each fixture creates a brand-new database, applies the versioned migrations in order,
and drops the database on teardown, so results are deterministic regardless of what was
applied before.

Everything is function-scoped on purpose: pytest-asyncio runs each test and its
function-scoped fixtures in a single per-test event loop, and asyncpg connections
cannot be shared across loops. Keep session-scoped async objects (pools) out of this
module.

Point the harness at a server with:

    TEST_DATABASE_ADMIN_URL=postgresql://user:pass@host:port/postgres

It defaults to the repository's local dev credentials (see backend/.env.example).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
SEED_DIR = Path(__file__).resolve().parents[1] / "seed"

ALL_TABLES = (
    "users",
    "templates",
    "sections",
    "items",
    "comments",
    "comment_options",
    "import_issues",
)

# Deterministic identities used by the RLS/ownership tests. These take the place of
# UserContext.user_id in the application layer (docs/DATABASE_DESIGN.md section 5).
USER_A_ID = "11111111-1111-1111-1111-111111111111"
USER_B_ID = "22222222-2222-2222-2222-222222222222"

AUTH_SETUP_SQL = """
CREATE SCHEMA auth;
CREATE TABLE auth.users (id uuid PRIMARY KEY);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
    LANGUAGE sql STABLE
AS $$
    SELECT NULLIF(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
"""


def _migration_files() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert files, f"no migration files found under {MIGRATIONS_DIR.as_posix()}"
    return files


async def _apply_migrations(conn: asyncpg.Connection) -> None:
    for path in _migration_files():
        await conn.execute(path.read_text(encoding="utf-8"))


def _database_url(name: str) -> str:
    base = ADMIN_DSN.rsplit("/", 1)[0]
    return f"{base}/{name}"


async def _create_database(name: str) -> None:
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


async def _drop_database(name: str) -> None:
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}"')
    finally:
        await conn.close()


@pytest.fixture()
async def database() -> AsyncIterator[asyncpg.Connection]:
    """Plain local/CI PostgreSQL: migrations applied, `auth` schema absent."""
    name = f"hi_schema_{uuid.uuid4().hex[:12]}"
    await _create_database(name)
    conn = await asyncpg.connect(_database_url(name))
    try:
        await _apply_migrations(conn)
        yield conn
    finally:
        await conn.close()
        await _drop_database(name)


def _grant_conformance_sql(roles: tuple[str, ...]) -> str:
    target = ", ".join(roles)
    return f"""
        GRANT USAGE ON SCHEMA public TO {target};
        GRANT USAGE ON SCHEMA auth TO {target};
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {target};
        GRANT EXECUTE ON FUNCTION auth.uid() TO {target};
    """


@pytest.fixture()
async def supabase_database() -> AsyncIterator[tuple[asyncpg.Connection, str, str]]:
    """Supabase-like environment: fake `auth` schema exists before migrations run.

    Both migrations then activate their Supabase-only pieces (auth sync trigger and the
    RLS policies). Two non-superuser roles are granted regular DML so that the policies
    are actually enforced against them (the backend's privileged connection would bypass
    RLS by design).
    """
    name = f"hi_supa_{uuid.uuid4().hex[:12]}"
    role_a = f"hi_app_{uuid.uuid4().hex[:8]}"
    role_b = f"hi_app_{uuid.uuid4().hex[:8]}"
    await _create_database(name)
    admin = await asyncpg.connect(ADMIN_DSN)
    try:
        await admin.execute(f"DROP ROLE IF EXISTS {role_a}")
        await admin.execute(f"DROP ROLE IF EXISTS {role_b}")
        await admin.execute(f"CREATE ROLE {role_a}")
        await admin.execute(f"CREATE ROLE {role_b}")
    finally:
        await admin.close()

    conn = await asyncpg.connect(_database_url(name))
    try:
        await conn.execute(AUTH_SETUP_SQL)
        await _apply_migrations(conn)
        await conn.execute(_grant_conformance_sql((role_a, role_b)))
        yield conn, role_a, role_b
    finally:
        await conn.close()
        await _drop_database(name)
        admin = await asyncpg.connect(ADMIN_DSN)
        try:
            await admin.execute(f"DROP ROLE IF EXISTS {role_a}")
            await admin.execute(f"DROP ROLE IF EXISTS {role_b}")
        finally:
            await admin.close()
