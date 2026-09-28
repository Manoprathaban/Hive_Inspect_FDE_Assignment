"""Row Level Security and ownership isolation tests.

The `supabase_database` fixture simulates Supabase: an `auth` schema exists before the
migrations run, so 0001 installs the auth sync trigger and 0002 installs RLS policies
keyed on `auth.uid()`. Two non-superuser roles then exercise the schema as if they were
authenticated application users, proving the cross-user isolation the assignment
requires (AGENTS.md section 21).

The `database` fixture (plain local/CI PostgreSQL, no `auth` schema) checks that the
same migrations are a deliberate no-op there and that the privileged connection still
sees everything by design.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
import pytest
from asyncpg.exceptions import PostgresError
from conftest import ALL_TABLES, USER_A_ID, USER_B_ID

EXPECTED_POLICIES = {
    "users": {"users_self"},
    "templates": {"templates_owner_all"},
    "sections": {"sections_owner_all"},
    "items": {"items_owner_all"},
    "comments": {"comments_owner_all"},
    "comment_options": {"comment_options_owner_all"},
    "import_issues": {"import_issues_owner_all"},
}

RLS_ERROR = "row-level security"


def uid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


async def fetch_rls_flags(conn: asyncpg.Connection) -> dict[str, bool]:
    rows = await conn.fetch(
        """
        SELECT relname, relrowsecurity
        FROM pg_class
        JOIN pg_namespace n ON n.oid = relnamespace
        WHERE n.nspname = 'public' AND relname = ANY($1::text[])
        ORDER BY relname
        """,
        list(ALL_TABLES),
    )
    return {str(r["relname"]): bool(r["relrowsecurity"]) for r in rows}


async def fetch_policies(conn: asyncpg.Connection) -> dict[str, set[str]]:
    rows = await conn.fetch(
        """
        SELECT tablename, policyname
        FROM pg_policies
        WHERE schemaname = 'public'
        ORDER BY tablename, policyname
        """
    )
    result: dict[str, set[str]] = {}
    for row in rows:
        result.setdefault(str(row["tablename"]), set()).add(str(row["policyname"]))
    return result


@asynccontextmanager
async def identity(
    conn: asyncpg.Connection, role: str, user_id: str
) -> AsyncIterator[asyncpg.Connection]:
    """Run the wrapped statements as `role` with auth.uid() == user_id."""
    async with conn.transaction():
        await conn.execute(f"SET LOCAL ROLE {role}")
        # `SET LOCAL request.jwt.claim.sub = $1` is not valid SQL; set_config is the
        # parameter-safe form, and the last argument makes it local to the transaction.
        await conn.execute("SELECT set_config('request.jwt.claim.sub', $1, true)", user_id)
        yield conn


async def insert_template(conn: asyncpg.Connection, owner_id: str) -> str:
    # templates.owner_id is a real FK to users (design section 4), so the owner identity
    # row must exist first — mirroring what the auth-sync trigger creates in production.
    await conn.execute(
        "INSERT INTO users (id) VALUES ($1) ON CONFLICT (id) DO NOTHING", uid(owner_id)
    )
    return str(
        await conn.fetchval(
            "INSERT INTO templates (owner_id, name, source) " "VALUES ($1, $2, $3) RETURNING id",
            uid(owner_id),
            "Private",
            "spectora",
        )
    )


async def test_rls_enabled_with_documented_policies(supabase_database) -> None:
    conn, _role_a, _role_b = supabase_database
    flags = await fetch_rls_flags(conn)
    assert flags == {table: True for table in ALL_TABLES}
    policies = await fetch_policies(conn)
    assert policies == EXPECTED_POLICIES


async def test_auth_sync_trigger_installed_with_auth_schema(supabase_database) -> None:
    conn, _role_a, _role_b = supabase_database
    name = await conn.fetchval(
        "SELECT tgname FROM pg_trigger WHERE tgname = 'on_auth_user_created'"
    )
    assert name == "on_auth_user_created"


async def test_rls_is_a_noop_on_plain_postgres(database: asyncpg.Connection) -> None:
    flags = await fetch_rls_flags(database)
    assert flags == {table: False for table in ALL_TABLES}
    policies = await fetch_policies(database)
    assert policies == {}


async def test_privileged_connection_bypasses_rls(supabase_database) -> None:
    """The backend/service-role path bypasses RLS by design (design section 6)."""
    conn, _role_a, _role_b = supabase_database
    template_id = await insert_template(conn, USER_A_ID)
    count = await conn.fetchval("SELECT count(*) FROM templates WHERE id = $1", uid(template_id))
    assert count == 1


async def test_user_cannot_read_another_users_data(supabase_database) -> None:
    conn, _role_a, role_b = supabase_database
    template_id = await insert_template(conn, USER_A_ID)
    await conn.execute(
        "INSERT INTO sections (template_id, name, display_order) VALUES ($1, $2, $3)",
        uid(template_id),
        "A section",
        0,
    )

    async with identity(conn, role_b, USER_B_ID):
        templates = await conn.fetch("SELECT id FROM templates")
        sections = await conn.fetch("SELECT id FROM sections")
        assert templates == []
        assert sections == []


async def test_user_cannot_insert_under_another_users_template(
    supabase_database,
) -> None:
    conn, _role_a, role_b = supabase_database
    template_id = await insert_template(conn, USER_A_ID)
    async with identity(conn, role_b, USER_B_ID):
        with pytest.raises(PostgresError, match=RLS_ERROR):
            await conn.execute(
                "INSERT INTO sections (template_id, name, display_order) " "VALUES ($1, $2, $3)",
                uid(template_id),
                "Sneaky",
                0,
            )


async def test_user_cannot_update_or_delete_another_users_template(
    supabase_database,
) -> None:
    conn, role_a, role_b = supabase_database
    template_id = await insert_template(conn, USER_A_ID)
    async with identity(conn, role_b, USER_B_ID):
        updated = await conn.execute(
            "UPDATE templates SET name = $1 WHERE id = $2", "Hijacked", uid(template_id)
        )
        assert updated == "UPDATE 0"
        deleted = await conn.execute("DELETE FROM templates WHERE id = $1", uid(template_id))
        assert deleted == "DELETE 0"
    async with identity(conn, role_a, USER_A_ID):
        name = await conn.fetchval("SELECT name FROM templates WHERE id = $1", uid(template_id))
        assert name == "Private"


async def test_user_can_build_and_read_own_tree(supabase_database) -> None:
    conn, role_a, _role_b = supabase_database
    async with identity(conn, role_a, USER_A_ID):
        await conn.execute("INSERT INTO users (id) VALUES ($1)", uid(USER_A_ID))
        template_id = await conn.fetchval(
            "INSERT INTO templates (owner_id, name, source) VALUES ($1, $2, $3) RETURNING id",
            uid(USER_A_ID),
            "Mine",
            "spectora",
        )
        section_id = await conn.fetchval(
            "INSERT INTO sections (template_id, name, display_order) "
            "VALUES ($1, $2, $3) RETURNING id",
            template_id,
            "S",
            0,
        )
        item_id = await conn.fetchval(
            "INSERT INTO items (section_id, name, display_order) VALUES ($1, $2, $3) RETURNING id",
            section_id,
            "I",
            0,
        )
        comment_id = await conn.fetchval(
            "INSERT INTO comments (item_id, name, comment_type, answer_type, display_order) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            item_id,
            "C",
            "info",
            "text",
            0,
        )
        await conn.execute(
            "INSERT INTO comment_options (comment_id, option_type, value, display_order) "
            "VALUES ($1, $2, $3, $4)",
            comment_id,
            "unit_type",
            "sqft",
            0,
        )

    async with identity(conn, role_a, USER_A_ID):
        templates = await conn.fetch("SELECT id FROM templates")
        sections = await conn.fetch("SELECT id FROM sections")
        items = await conn.fetch("SELECT id FROM items")
        comments = await conn.fetch("SELECT id FROM comments")
        options = await conn.fetch("SELECT id FROM comment_options")
        assert len(templates) == len(sections) == len(items) == 1
        assert len(comments) == len(options) == 1


async def test_user_cannot_move_section_under_foreign_template(
    supabase_database,
) -> None:
    conn, _role_a, role_b = supabase_database
    foreign = await insert_template(conn, USER_A_ID)
    my = await insert_template(conn, USER_B_ID)
    async with identity(conn, role_b, USER_B_ID):
        section_id = await conn.fetchval(
            "INSERT INTO sections (template_id, name, display_order) "
            "VALUES ($1, $2, $3) RETURNING id",
            uid(my),
            "Mine",
            0,
        )
    async with identity(conn, role_b, USER_B_ID):
        with pytest.raises(PostgresError, match=RLS_ERROR):
            await conn.execute(
                "UPDATE sections SET template_id = $1 WHERE id = $2",
                uid(foreign),
                section_id,
            )


async def test_users_self_policy(supabase_database) -> None:
    conn, role_a, role_b = supabase_database
    async with identity(conn, role_a, USER_A_ID):
        await conn.execute("INSERT INTO users (id) VALUES ($1)", uid(USER_A_ID))
    async with identity(conn, role_b, USER_B_ID):
        await conn.execute("INSERT INTO users (id) VALUES ($1)", uid(USER_B_ID))
    async with identity(conn, role_a, USER_A_ID):
        own = await conn.fetchval("SELECT count(*) FROM users WHERE id = $1", uid(USER_A_ID))
        others = await conn.fetchval("SELECT count(*) FROM users WHERE id = $1", uid(USER_B_ID))
        assert own == 1
        assert others == 0


async def test_issue_cannot_be_recorded_under_foreign_template(
    supabase_database,
) -> None:
    conn, _role_a, role_b = supabase_database
    template_id = await insert_template(conn, USER_A_ID)
    async with identity(conn, role_b, USER_B_ID):
        with pytest.raises(PostgresError, match=RLS_ERROR):
            await conn.execute(
                "INSERT INTO import_issues (template_id, issue_type, message) "
                "VALUES ($1, $2, $3)",
                uid(template_id),
                "SOURCE_DATA_MISSING",
                "nope",
            )
