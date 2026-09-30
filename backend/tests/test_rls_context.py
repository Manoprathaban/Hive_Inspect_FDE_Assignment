"""Unit tests for the RLS request-scoping helpers.

These run offline: they assert the statements issued against a connection, not database
behaviour. The database-level proof that those statements actually make the 0002 policies
bind lives in ``database/tests/test_rls.py`` (``test_app_role_created_by_0003`` and
``test_policies_bind_on_the_app_role_request_path``) and in
``tests/test_postgres_repository.py``.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import pytest

from app.adapters.repositories.postgres import PostgresTemplateRepository
from app.infrastructure.database import apply_rls_context, owner_scoped_connection

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")


class _RecordingConnection:
    """Minimal stand-in that records the statements and parameters it is handed."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, Any] | None]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        self.statements.append((str(statement), params))
        return None

    def begin(self) -> _Transaction:
        return _Transaction(self)


class _Transaction:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    async def __aenter__(self) -> Any:
        return self._conn

    async def __aexit__(self, *_: object) -> None:
        return None


class _Engine:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def connect(self) -> _Transaction:
        return _Transaction(self._conn)

    def begin(self) -> _Transaction:
        return _Transaction(self._conn)


def test_apply_rls_context_assumes_role_and_publishes_claims() -> None:
    conn = _RecordingConnection()

    asyncio.run(apply_rls_context(conn, owner_id=USER, app_role="hive_app"))  # type: ignore[arg-type]

    rendered = [sql for sql, _ in conn.statements]
    assert rendered[0] == 'SET LOCAL ROLE "hive_app"'
    assert rendered[1].startswith("SELECT set_config('request.jwt.claims'")
    assert rendered[2].startswith("SELECT set_config('request.jwt.claim.sub'")
    # The claims must be transaction-local: a pooled connection is reused by the next
    # request, and a session-level setting would hand it the previous user's identity.
    for sql in rendered[1:]:
        assert "true)" in sql, f"claims must be transaction-local: {sql}"

    claims = json.loads(conn.statements[1][1]["claims"])  # type: ignore[index]
    assert claims == {"sub": str(USER), "role": "authenticated"}
    assert conn.statements[2][1]["sub"] == str(USER)  # type: ignore[index]


@pytest.mark.parametrize(
    "app_role",
    [
        'hive_app"; SET ROLE postgres; --',
        "hive_app; DROP TABLE templates",
        "hive app",
        "",
        "1bad",
        "bad-role",
    ],
)
def test_apply_rls_context_rejects_an_unsafe_role_name(app_role: str) -> None:
    """The role reaches SQL through SET ROLE, which takes no bind parameters.

    It comes from the environment, so a malformed or injected value must fail loudly
    instead of being interpolated into the statement.
    """

    conn = _RecordingConnection()

    with pytest.raises(ValueError, match="invalid role name"):
        asyncio.run(apply_rls_context(conn, owner_id=USER, app_role=app_role))  # type: ignore[arg-type]

    assert conn.statements == [], "no statement may be issued for a rejected role name"


def test_owner_scoped_connection_primes_the_context_before_yielding() -> None:
    conn = _RecordingConnection()
    engine = _Engine(conn)

    async def scenario() -> None:
        async with owner_scoped_connection(  # type: ignore[arg-type]
            engine, owner_id=USER, app_role="hive_app"
        ) as scoped:
            assert scoped is conn
            # Scoping happens before the body runs, not after the caller issues a query.
            assert conn.statements[0][0] == 'SET LOCAL ROLE "hive_app"'

    asyncio.run(scenario())
    assert len(conn.statements) == 3


def test_repository_without_an_app_role_uses_an_ordinary_transaction() -> None:
    """``DB_APP_ROLE=`` must degrade to the pre-0003 behaviour, not to a broken query."""

    class _PlainEngine:
        def begin(self) -> str:
            return "plain-transaction"

    repository = PostgresTemplateRepository(_PlainEngine(), app_role=None)  # type: ignore[arg-type]
    assert repository._owner_connection(USER) == "plain-transaction"

    scoped = PostgresTemplateRepository(  # type: ignore[arg-type]
        _PlainEngine(), app_role="hive_app"
    )._owner_connection(USER)
    # An async context manager rather than the bare transaction, i.e. the scoped path.
    assert hasattr(scoped, "__aenter__")
    assert not isinstance(scoped, str)
