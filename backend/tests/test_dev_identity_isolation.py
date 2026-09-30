"""End-to-end tenant isolation for development credentials, against real PostgreSQL.

Regression cover for the reported bug: signing in with different credentials handed over one
shared user's templates, because the development provider ignored the credential and always
resolved the same seeded identity.

Each test builds a throwaway database with the migrations applied, drives the real FastAPI
app over ASGI (no repository stubbing, so the auth path, the ``public.users`` provisioning
and the RLS policies all run), then drops the database. Skipped when no server is reachable.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.adapters.authentication.dev import DEV_USER_EMAIL, DEV_USER_ID, derive_dev_user_id
from app.adapters.repositories.postgres import PostgresTemplateRepository
from app.api.dependencies.auth import get_database_engine
from app.api.dependencies.providers import get_template_repository
from app.domain.models.template import Template
from app.infrastructure.database import owner_scoped_connection
from app.main import create_app

ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "database" / "migrations"
APP_ROLE = "hive_app"

DEMO = f"dev:{DEV_USER_EMAIL}"
STRANGER = "dev:stranger@example.test"

_AUTH_SCHEMA_STUB = """
CREATE SCHEMA auth;
CREATE TABLE auth.users (id uuid PRIMARY KEY);
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT NULLIF(
        COALESCE(
            current_setting('request.jwt.claim.sub', true),
            current_setting('request.jwt.claims', true)::jsonb ->> 'sub'
        ),
        ''
    )::uuid
$$;
"""


def _server_reachable() -> bool:
    async def _try() -> bool:
        try:
            conn = await asyncio.wait_for(asyncpg.connect(ADMIN_DSN), timeout=3)
        except Exception:
            return False
        await conn.close()
        return True

    try:
        return asyncio.run(_try())
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _server_reachable(),
    reason="no reachable PostgreSQL server; set TEST_DATABASE_ADMIN_URL to enable",
)


@asynccontextmanager
async def _live_client() -> AsyncIterator[httpx.AsyncClient]:
    """A throwaway database plus an API client wired to it, with RLS active."""

    name = f"hi_identity_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(ADMIN_DSN)
    plain_base = ADMIN_DSN.rsplit("/", 1)[0]
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()

    engine: AsyncEngine | None = None
    try:
        dsn = f"{plain_base}/{name}"
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(_AUTH_SCHEMA_STUB)
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                await conn.execute(path.read_text(encoding="utf-8"))
        finally:
            await conn.close()

        engine = create_async_engine("postgresql+asyncpg://" + dsn.split("://", 1)[1])
        app = create_app()
        app.dependency_overrides[get_template_repository] = lambda: PostgresTemplateRepository(
            engine, app_role=APP_ROLE
        )
        app.dependency_overrides[get_database_engine] = lambda: engine
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://identity.test"
        ) as client:
            client.engine = engine  # type: ignore[attr-defined]
            yield client
    finally:
        if engine is not None:
            await engine.dispose()
        admin = await asyncpg.connect(ADMIN_DSN)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        finally:
            await admin.close()


async def _seed_demo_template(client: httpx.AsyncClient) -> uuid.UUID:
    """Give the demo tenant one template, written through the scoped repository.

    The identity's ``public.users`` row does not exist in a fresh database, so the first
    request is made before the write — exactly the order a real user's session follows.
    """

    assert (await client.get("/api/templates", headers=_auth(DEMO))).status_code == 200
    engine: AsyncEngine = client.engine  # type: ignore[attr-defined]
    repository = PostgresTemplateRepository(engine, app_role=APP_ROLE)
    template = Template(name="Demo tenant template")
    saved = await repository.save(template, owner_id=DEV_USER_ID)
    return saved.id


def test_two_credentials_are_two_tenants() -> None:
    """The reported bug: a second sign-in must not inherit the first one's templates."""

    async def _run() -> None:
        async with _live_client() as client:
            await _seed_demo_template(client)

            demo = await client.get("/api/templates", headers=_auth(DEMO))
            stranger = await client.get("/api/templates", headers=_auth(STRANGER))

            assert demo.status_code == 200
            assert [t["name"] for t in demo.json()] == ["Demo tenant template"]
            assert stranger.status_code == 200
            assert stranger.json() == []

    asyncio.run(_run())


def test_a_tenant_cannot_read_another_tenants_template() -> None:
    async def _run() -> None:
        async with _live_client() as client:
            template_id = await _seed_demo_template(client)
            response = await client.get(f"/api/templates/{template_id}", headers=_auth(STRANGER))
            assert response.status_code == 404

    asyncio.run(_run())


def test_each_credential_gets_a_stable_identity_across_requests() -> None:
    async def _run() -> None:
        async with _live_client() as client:
            first = await client.get("/api/templates", headers=_auth(STRANGER))
            second = await client.get("/api/templates", headers=_auth(STRANGER))
            assert first.status_code == second.status_code == 200

            engine: AsyncEngine = client.engine  # type: ignore[attr-defined]
            async with engine.begin() as conn:
                rows = (
                    (await conn.execute(text("SELECT id FROM public.users ORDER BY id")))
                    .scalars()
                    .all()
                )
            expected = derive_dev_user_id(STRANGER)
            assert expected in {uuid.UUID(str(r)) for r in rows}

    asyncio.run(_run())


def test_a_new_identity_is_provisioned_and_can_own_a_template() -> None:
    """Provisioning must happen before a write, or the owner_id foreign key rejects it."""

    async def _run() -> None:
        async with _live_client() as client:
            # Any request provisions the identity's public.users row.
            assert (await client.get("/api/templates", headers=_auth(STRANGER))).status_code == 200

            engine: AsyncEngine = client.engine  # type: ignore[attr-defined]
            owner = derive_dev_user_id(STRANGER)
            repository = PostgresTemplateRepository(engine, app_role=APP_ROLE)
            saved = await repository.save(Template(name="Stranger"), owner_id=owner)

            listed = await client.get("/api/templates", headers=_auth(STRANGER))
            assert [t["id"] for t in listed.json()] == [str(saved.id)]

    asyncio.run(_run())


def test_rls_filters_a_second_tenants_rows_for_a_real_write() -> None:
    async def _run() -> None:
        async with _live_client() as client:
            template_id = await _seed_demo_template(client)
            engine: AsyncEngine = client.engine  # type: ignore[attr-defined]
            stranger_id = derive_dev_user_id(STRANGER)

            async with owner_scoped_connection(
                engine, owner_id=stranger_id, app_role=APP_ROLE
            ) as conn:
                visible = (
                    await conn.execute(
                        text("SELECT id FROM public.templates WHERE id = :id"),
                        {"id": template_id},
                    )
                ).all()
                assert visible == []

    asyncio.run(_run())


def test_missing_credential_is_rejected() -> None:
    async def _run() -> None:
        async with _live_client() as client:
            response = await client.get("/api/templates")
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    asyncio.run(_run())


def test_blank_credential_is_rejected() -> None:
    async def _run() -> None:
        async with _live_client() as client:
            response = await client.get("/api/templates", headers={"Authorization": "Bearer  "})
            assert response.status_code == 401
            assert response.json()["error"]["code"] in {
                "AUTHENTICATION_REQUIRED",
                "INVALID_TOKEN",
            }

    asyncio.run(_run())


def _auth(credential: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}"}
