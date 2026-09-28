"""Behavioral tests for the schema, run on the live database.

Covers the design decisions in docs/DATABASE_DESIGN.md sections 4, 11, 12, 13:
cascade and SET NULL deletes, FK integrity, explicit zero-based ordering (with UNIQUE
where the design says so and plain order values where it does not), CHECK constraints,
documented defaults, the `updated_at` triggers, transactions, and the dev seed.
"""

from __future__ import annotations

import uuid

import asyncpg
import pytest
from asyncpg.exceptions import (
    CheckViolationError,
    ForeignKeyViolationError,
    UniqueViolationError,
)
from conftest import SEED_DIR


async def seed_tree(conn: asyncpg.Connection, owner_id: str | None = None) -> dict:
    """Insert one owner/user + template + section + item + comment + option."""
    if owner_id is None:
        owner_id = str(uuid.uuid4())
    owner = uuid.UUID(owner_id)
    await conn.execute("INSERT INTO users (id) VALUES ($1)", owner)
    template_id = await conn.fetchval(
        "INSERT INTO templates (owner_id, name, source) VALUES ($1, $2, $3) RETURNING id",
        owner,
        "Inspection",
        "spectora",
    )
    section_id = await conn.fetchval(
        "INSERT INTO sections (template_id, name, display_order) "
        "VALUES ($1, $2, $3) RETURNING id",
        template_id,
        "Basement",
        0,
    )
    item_id = await conn.fetchval(
        "INSERT INTO items (section_id, name, display_order) VALUES ($1, $2, $3) RETURNING id",
        section_id,
        "Sump pump",
        0,
    )
    comment_id = await conn.fetchval(
        "INSERT INTO comments (item_id, name, comment_type, answer_type, display_order) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id",
        item_id,
        "Crack",
        "defect",
        "boolean",
        0,
    )
    option_id = await conn.fetchval(
        "INSERT INTO comment_options (comment_id, option_type, value, display_order) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        comment_id,
        "multiple_choice",
        "Yes",
        0,
    )
    return {
        "owner": owner,
        "template_id": template_id,
        "section_id": section_id,
        "item_id": item_id,
        "comment_id": comment_id,
        "option_id": option_id,
    }


async def test_updated_at_is_maintained_on_every_timestamped_table(
    database: asyncpg.Connection,
) -> None:
    ids = await seed_tree(database)
    cases = [
        ("users", "id", ids["owner"]),
        ("templates", "id", ids["template_id"]),
        ("sections", "id", ids["section_id"]),
        ("items", "id", ids["item_id"]),
        ("comments", "id", ids["comment_id"]),
    ]
    for table, pk_column, pk_value in cases:
        before = await database.fetchval(
            f"SELECT updated_at FROM {table} WHERE {pk_column} = $1", pk_value
        )
        await database.execute(
            f"UPDATE {table} SET {pk_column} = {pk_column} WHERE {pk_column} = $1",
            pk_value,
        )
        after = await database.fetchval(
            f"SELECT updated_at FROM {table} WHERE {pk_column} = $1", pk_value
        )
        assert after > before, table


async def test_import_issues_has_no_updated_at(database: asyncpg.Connection) -> None:
    columns = {
        str(r["column_name"])
        for r in await database.fetch(
            """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'import_issues'
        """
        )
    }
    assert "created_at" in columns
    assert "updated_at" not in columns


async def test_deleting_user_cascades_to_templates(database: asyncpg.Connection) -> None:
    ids = await seed_tree(database)
    await database.execute("DELETE FROM users WHERE id = $1", ids["owner"])
    for table in ("templates", "sections", "items", "comments", "comment_options"):
        count = await database.fetchval(f"SELECT count(*) FROM {table}")
        assert count == 0, table


async def test_deleting_template_cascades_the_whole_tree(
    database: asyncpg.Connection,
) -> None:
    ids = await seed_tree(database)
    await database.execute("DELETE FROM templates WHERE id = $1", ids["template_id"])
    for table in ("sections", "items", "comments", "comment_options", "import_issues"):
        count = await database.fetchval(f"SELECT count(*) FROM {table}")
        assert count == 0, table


async def test_deleting_a_section_removes_only_its_descendants(
    database: asyncpg.Connection,
) -> None:
    ids = await seed_tree(database)
    await database.execute("DELETE FROM sections WHERE id = $1", ids["section_id"])
    assert await database.fetchval("SELECT count(*) FROM items") == 0
    assert await database.fetchval("SELECT count(*) FROM comments") == 0
    assert (
        await database.fetchval("SELECT count(*) FROM templates WHERE id = $1", ids["template_id"])
        == 1
    )


async def test_deleting_original_sets_copied_from_null(
    database: asyncpg.Connection,
) -> None:
    ids = await seed_tree(database)
    copy_id = await database.fetchval(
        "INSERT INTO templates (owner_id, name, source, copied_from_id) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        ids["owner"],
        "Copy",
        "spectora",
        ids["template_id"],
    )
    await database.execute("DELETE FROM templates WHERE id = $1", ids["template_id"])
    copied_from = await database.fetchval(
        "SELECT copied_from_id FROM templates WHERE id = $1", copy_id
    )
    assert copied_from is None


async def test_fk_rejects_orphan_child(database: asyncpg.Connection) -> None:
    with pytest.raises(ForeignKeyViolationError):
        await database.execute(
            "INSERT INTO comments (item_id, name, comment_type, answer_type, display_order) "
            "VALUES ($1, $2, $3, $4, $5)",
            uuid.uuid4(),
            "Orphan",
            "info",
            "text",
            0,
        )


async def test_section_ordering_is_unique_per_template(
    database: asyncpg.Connection,
) -> None:
    ids = await seed_tree(database)
    with pytest.raises(UniqueViolationError):
        await database.execute(
            "INSERT INTO sections (template_id, name, display_order) VALUES ($1, $2, $3)",
            ids["template_id"],
            "Duplicate order",
            0,
        )


async def test_item_ordering_is_unique_per_section(database: asyncpg.Connection) -> None:
    ids = await seed_tree(database)
    with pytest.raises(UniqueViolationError):
        await database.execute(
            "INSERT INTO items (section_id, name, display_order) VALUES ($1, $2, $3)",
            ids["section_id"],
            "Duplicate order",
            0,
        )


async def test_option_ordering_is_unique_per_comment(database: asyncpg.Connection) -> None:
    ids = await seed_tree(database)
    with pytest.raises(UniqueViolationError):
        await database.execute(
            "INSERT INTO comment_options (comment_id, option_type, value, display_order) "
            "VALUES ($1, $2, $3, $4)",
            ids["comment_id"],
            "multiple_choice",
            "Dupe",
            0,
        )


async def test_comments_may_repeat_display_order(database: asyncpg.Connection) -> None:
    """comments.display_order is plain (design section 11): duplicates are allowed."""
    ids = await seed_tree(database)
    second = await database.fetchval(
        "INSERT INTO comments (item_id, name, comment_type, answer_type, display_order) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id",
        ids["item_id"],
        "Tie",
        "info",
        "text",
        0,
    )
    assert second is not None
    count = await database.fetchval(
        "SELECT count(*) FROM comments WHERE item_id = $1 AND display_order = 0",
        ids["item_id"],
    )
    assert count == 2


async def test_negative_display_order_is_rejected(database: asyncpg.Connection) -> None:
    ids = await seed_tree(database)
    cases = [
        (
            "INSERT INTO sections (template_id, name, display_order) VALUES ($1, $2, $3)",
            (ids["template_id"], "bad", -1),
        ),
        (
            "INSERT INTO items (section_id, name, display_order) VALUES ($1, $2, $3)",
            (ids["section_id"], "bad", -1),
        ),
        (
            "INSERT INTO comments (item_id, name, comment_type, answer_type, display_order) "
            "VALUES ($1, $2, $3, $4, $5)",
            (ids["item_id"], "bad", "info", "text", -1),
        ),
        (
            "INSERT INTO comment_options (comment_id, option_type, value, display_order) "
            "VALUES ($1, $2, $3, $4)",
            (ids["comment_id"], "multiple_choice", "bad", -1),
        ),
    ]
    for sql, args in cases:
        with pytest.raises(CheckViolationError):
            await database.execute(sql, *args)


async def test_comment_category_is_restricted(database: asyncpg.Connection) -> None:
    ids = await seed_tree(database)
    with pytest.raises(CheckViolationError):
        await database.execute(
            "INSERT INTO comments (item_id, name, category, comment_type, answer_type, "
            "display_order) VALUES ($1, $2, $3, $4, $5, $6)",
            ids["item_id"],
            "Bad category",
            2,
            "info",
            "text",
            0,
        )


async def test_documented_defaults(database: asyncpg.Connection) -> None:
    ids = await seed_tree(database)

    comment = await database.fetchrow(
        "SELECT content, display_order FROM comments WHERE id = $1", ids["comment_id"]
    )
    assert comment["content"] == ""
    assert comment["display_order"] == 0

    option = await database.fetchrow(
        "SELECT display_order FROM comment_options WHERE id = $1", ids["option_id"]
    )
    assert option["display_order"] == 0

    issue_id = await database.fetchval(
        "INSERT INTO import_issues (template_id, issue_type, message) "
        "VALUES ($1, $2, $3) RETURNING id",
        ids["template_id"],
        "SOURCE_DATA_MISSING",
        "no name",
    )
    severity = await database.fetchval("SELECT severity FROM import_issues WHERE id = $1", issue_id)
    assert severity == "warning"


async def test_ordering_sample_returns_display_order_sequence(
    database: asyncpg.Connection,
) -> None:
    ids = await seed_tree(database)
    # seed_tree already created one section at order 0; drop the seed tree's sections so
    # every order below is unique per template.
    await database.execute("DELETE FROM sections WHERE template_id = $1", ids["template_id"])
    for order in (2, 0, 1):
        await database.execute(
            "INSERT INTO sections (template_id, name, display_order) VALUES ($1, $2, $3)",
            ids["template_id"],
            f"Section {order}",
            order,
        )
    orders = await database.fetch(
        "SELECT display_order FROM sections WHERE template_id = $1 ORDER BY display_order",
        ids["template_id"],
    )
    assert [r["display_order"] for r in orders] == [0, 1, 2]


async def test_transaction_rollback_leaves_no_partial_tree(
    database: asyncpg.Connection,
) -> None:
    owner = str(uuid.uuid4())
    transaction = database.transaction()
    await transaction.start()
    await database.execute("INSERT INTO users (id) VALUES ($1)", uuid.UUID(owner))
    await database.execute(
        "INSERT INTO templates (owner_id, name, source) VALUES ($1, $2, $3)",
        uuid.UUID(owner),
        "Rollback",
        "spectora",
    )
    await transaction.rollback()
    assert await database.fetchval("SELECT count(*) FROM templates") == 0
    assert await database.fetchval("SELECT count(*) FROM users") == 0


async def test_dev_seed_is_idempotent(database: asyncpg.Connection) -> None:
    seed_path = SEED_DIR / "dev_auth.sql"
    sql = seed_path.read_text(encoding="utf-8")
    await database.execute(sql)
    await database.execute(sql)
    count = await database.fetchval(
        "SELECT count(*) FROM users WHERE id = " "'00000000-0000-0000-0000-000000000001'"
    )
    assert count == 1
