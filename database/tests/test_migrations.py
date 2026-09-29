"""Audit the schema produced by the migrations against docs/DATABASE_DESIGN.md.

Each test reads the live catalogs and compares them to the documented schema: enum
value sets, table/column shapes, primary keys, foreign keys with ON DELETE rules,
ordering UNIQUE constraints, CHECK constraints, the explicit index set, and the
`updated_at` triggers.
"""

from __future__ import annotations

from collections import defaultdict

import asyncpg

ALL_TABLES = (
    "users",
    "templates",
    "sections",
    "items",
    "comments",
    "comment_options",
    "import_issues",
)

# Enum name -> ordered members, per DATABASE_DESIGN.md section 3.
EXPECTED_ENUMS = {
    "comment_type": ["info", "limit", "defect"],
    "answer_type": ["boolean", "checkbox", "date", "number", "range", "text"],
    "option_type": ["multiple_choice", "unit_type"],
    "issue_type": [
        "SOURCE_DATA_MISSING",
        "UNSUPPORTED_CONTENT",
        "INVALID_SOURCE_DATA",
    ],
    "issue_severity": ["info", "warning", "error"],
}

TS = "timestamp with time zone"

# table -> {column: (information_schema data_type, nullable, enum udt name or None)}
EXPECTED_COLUMNS: dict[str, dict[str, tuple[str, bool, str | None]]] = {
    "users": {
        "id": ("uuid", False, None),
        "created_at": (TS, False, None),
        "updated_at": (TS, False, None),
    },
    "templates": {
        "id": ("uuid", False, None),
        "owner_id": ("uuid", False, None),
        "name": ("text", False, None),
        "source": ("text", False, None),
        "source_filename": ("text", True, None),
        "copied_from_id": ("uuid", True, None),
        "created_at": (TS, False, None),
        "updated_at": (TS, False, None),
    },
    "sections": {
        "id": ("uuid", False, None),
        "template_id": ("uuid", False, None),
        "name": ("text", False, None),
        "display_order": ("integer", False, None),
        "created_at": (TS, False, None),
        "updated_at": (TS, False, None),
    },
    "items": {
        "id": ("uuid", False, None),
        "section_id": ("uuid", False, None),
        "name": ("text", False, None),
        "display_order": ("integer", False, None),
        "created_at": (TS, False, None),
        "updated_at": (TS, False, None),
    },
    "comments": {
        "id": ("uuid", False, None),
        "item_id": ("uuid", False, None),
        "name": ("text", False, None),
        "content": ("text", False, None),
        "comment_type": ("USER-DEFINED", False, "comment_type"),
        "category": ("smallint", True, None),
        "answer_type": ("USER-DEFINED", False, "answer_type"),
        "display_order": ("integer", False, None),
        "recommendation": ("text", True, None),
        "default_value": ("text", True, None),
        "default_value_2": ("text", True, None),
        "default_unit_type": ("text", True, None),
        "estimate_min": ("numeric", True, None),
        "estimate_max": ("numeric", True, None),
        "source_row": ("integer", True, None),
        "created_at": (TS, False, None),
        "updated_at": (TS, False, None),
    },
    "comment_options": {
        "id": ("uuid", False, None),
        "comment_id": ("uuid", False, None),
        "option_type": ("USER-DEFINED", False, "option_type"),
        "value": ("text", False, None),
        "display_order": ("integer", False, None),
    },
    "import_issues": {
        "id": ("uuid", False, None),
        "template_id": ("uuid", False, None),
        "source_row": ("integer", True, None),
        "source_field": ("text", True, None),
        "issue_type": ("USER-DEFINED", False, "issue_type"),
        "message": ("text", False, None),
        "raw_value": ("text", True, None),
        "severity": ("USER-DEFINED", False, "issue_severity"),
        "created_at": (TS, False, None),
    },
}

# (source table, source column, referenced table, referenced column, ON DELETE)
# per DATABASE_DESIGN.md section 4.
EXPECTED_FKS = {
    ("templates", "owner_id"): ("users", "id", "cascade"),
    ("templates", "copied_from_id"): ("templates", "id", "set null"),
    ("sections", "template_id"): ("templates", "id", "cascade"),
    ("items", "section_id"): ("sections", "id", "cascade"),
    ("comments", "item_id"): ("items", "id", "cascade"),
    ("comment_options", "comment_id"): ("comments", "id", "cascade"),
    ("import_issues", "template_id"): ("templates", "id", "cascade"),
}

# Ordering UNIQUEs per DATABASE_DESIGN.md sections 3 and 7.
EXPECTED_UNIQUES = {
    "sections": ("template_id", "display_order"),
    "items": ("section_id", "display_order"),
    "comment_options": ("comment_id", "option_type", "display_order"),
}

# CHECK constraints defined on display_order (design section 11) and comments.category.
DISPLAY_ORDER_TABLES = ("sections", "items", "comments", "comment_options")

# Explicit CREATE INDEX statements per design section 7. The ordering UNIQUE
# constraints double as the FK-side indexes, so no other indexes are created.
EXPECTED_NAMED_INDEXES = {
    "templates_owner_id_idx": "owner_id",
    "comments_item_order_idx": "item_id",
    "import_issues_template_id_idx": "template_id",
}

# Tables carrying a `created_at` column (all except comment_options, which the design
# deliberately leaves untimestamped — design sections 1 and 3).
CREATED_AT_TABLES = ("users", "templates", "sections", "items", "comments", "import_issues")

# Tables carrying an `updated_at` column must also carry the set_updated_at trigger.
TIMESTAMPED_TABLES = ("users", "templates", "sections", "items", "comments")


async def test_enum_value_sets(database: asyncpg.Connection) -> None:
    rows = await database.fetch(
        """
        SELECT t.typname AS name, e.enumlabel AS label
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace AND n.nspname = 'public'
        JOIN pg_enum e ON e.enumtypid = t.oid
        ORDER BY t.typname, e.enumsortorder
        """
    )
    actual: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        actual[str(row["name"])].append(str(row["label"]))
    assert dict(actual) == EXPECTED_ENUMS


async def test_columns_match_design(database: asyncpg.Connection) -> None:
    rows = await database.fetch(
        """
        SELECT table_name, column_name, data_type, udt_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
        """
    )
    actual: dict[str, dict[str, tuple[str, bool, str | None]]] = {}
    for row in rows:
        table = str(row["table_name"])
        data_type = str(row["data_type"])
        udt = str(row["udt_name"]) if data_type == "USER-DEFINED" else None
        nullable = str(row["is_nullable"]) == "YES"
        actual.setdefault(table, {})[str(row["column_name"])] = (
            data_type,
            nullable,
            udt,
        )
    assert actual == EXPECTED_COLUMNS


async def test_documented_defaults(database: asyncpg.Connection) -> None:
    rows = await database.fetch(
        """
        SELECT table_name, column_name, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = ANY($1::text[])
          AND column_name IN ('created_at', 'updated_at', 'content',
                              'display_order', 'severity')
        ORDER BY table_name, column_name
        """,
        list(ALL_TABLES),
    )
    defaults = {(str(r["table_name"]), str(r["column_name"])): r["column_default"] for r in rows}

    for table in CREATED_AT_TABLES:
        assert defaults[(table, "created_at")] is not None
        assert "now()" in str(defaults[(table, "created_at")])
    for table in TIMESTAMPED_TABLES:
        assert "now()" in str(defaults[(table, "updated_at")])
    assert "'" in str(defaults[("comments", "content")])  # DEFAULT ''
    assert "0" in str(defaults[("comments", "display_order")])
    assert "0" in str(defaults[("comment_options", "display_order")])
    assert "warning" in str(defaults[("import_issues", "severity")])


async def test_primary_keys_are_single_id_columns(database: asyncpg.Connection) -> None:
    rows = await database.fetch(
        """
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON kcu.constraint_schema = tc.constraint_schema
         AND kcu.constraint_name = tc.constraint_name
         AND kcu.table_name = tc.table_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = 'public'
        ORDER BY tc.table_name, kcu.ordinal_position
        """
    )
    actual: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        actual[str(row["table_name"])].append(str(row["column_name"]))
    assert {t: ["id"] for t in ALL_TABLES} == dict(actual)


async def test_foreign_keys_match_design(database: asyncpg.Connection) -> None:
    rows = await database.fetch(
        """
        SELECT cl.relname AS table_name,
               a.attname AS column_name,
               cref.relname AS ref_table,
               af.attname AS ref_column,
               c.confdeltype AS on_delete
        FROM pg_constraint c
        JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace AND n.nspname = 'public'
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
        JOIN pg_class cref ON cref.oid = c.confrelid
        JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[1]
        WHERE c.contype = 'f'
        ORDER BY cl.relname, c.conname
        """
    )
    actual: dict[tuple[str, str], tuple[str, str, str]] = {}
    for row in rows:
        delete_rule = {
            b"c": "cascade",
            b"n": "set null",
            b"a": "no action",
            b"r": "restrict",
            b"d": "default",
        }[row["on_delete"]]
        actual[(str(row["table_name"]), str(row["column_name"]))] = (
            str(row["ref_table"]),
            str(row["ref_column"]),
            delete_rule,
        )
    assert actual == EXPECTED_FKS


async def test_ordering_unique_constraints(database: asyncpg.Connection) -> None:
    rows = await database.fetch(
        """
        SELECT cl.relname AS table_name,
               array_agg(a.attname ORDER BY u.ord) AS columns
        FROM pg_constraint c
        JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace AND n.nspname = 'public'
        JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS u(attnum, ord) ON TRUE
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = u.attnum
        WHERE c.contype = 'u'
        GROUP BY cl.relname, c.conname
        ORDER BY cl.relname
        """
    )
    actual = {str(r["table_name"]): [str(c) for c in r["columns"]] for r in rows}
    assert actual == {t: list(cols) for t, cols in EXPECTED_UNIQUES.items()}


async def test_check_constraints(database: asyncpg.Connection) -> None:
    rows = await database.fetch(
        """
        SELECT cl.relname AS table_name, pg_get_constraintdef(c.oid) AS definition
        FROM pg_constraint c
        JOIN pg_class cl ON cl.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace AND n.nspname = 'public'
        WHERE c.contype = 'c'
        ORDER BY cl.relname
        """
    )
    defs: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        defs[str(row["table_name"])].append(str(row["definition"]))

    for table in DISPLAY_ORDER_TABLES:
        assert any("display_order >= 0" in d for d in defs[table]), table

    category_defs = " ".join(defs["comments"]).lower()
    assert "category" in category_defs and "-1" in category_defs


async def test_index_set_matches_design(database: asyncpg.Connection) -> None:
    rows = await database.fetch(
        """
        SELECT ix.indexname, ix.indexdef
        FROM pg_indexes ix
        WHERE ix.schemaname = 'public'
        ORDER BY ix.indexname
        """
    )
    index_defs = {str(r["indexname"]): str(r["indexdef"]) for r in rows}

    for name, column in EXPECTED_NAMED_INDEXES.items():
        assert name in index_defs, f"missing index {name}"
        assert f"({column}" in index_defs[name], (name, index_defs[name])

    # No redundant single-column FK indexes on sections/items/comments/comment_options
    # (design section 7). These names must not exist.
    for forbidden in (
        "sections_template_id_idx",
        "items_section_id_idx",
        "comments_item_id_idx",
        "comment_options_comment_id_idx",
    ):
        assert forbidden not in index_defs, forbidden


async def test_updated_at_triggers_cover_every_timestamped_table(
    database: asyncpg.Connection,
) -> None:
    rows = await database.fetch(
        """
        SELECT cl.relname AS table_name, t.tgname, p.proname AS function_name
        FROM pg_trigger t
        JOIN pg_class cl ON cl.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = cl.relnamespace AND n.nspname = 'public'
        JOIN pg_proc p ON p.oid = t.tgfoid
        WHERE NOT t.tgisinternal
        ORDER BY cl.relname
        """
    )
    triggers = {(str(r["table_name"]), str(r["tgname"])): str(r["function_name"]) for r in rows}

    for table in TIMESTAMPED_TABLES:
        assert triggers[(table, f"{table}_set_updated_at")] == "set_updated_at", table

    # import_issues has a created_at only and must not carry the trigger.
    assert (
        "import_issues",
        "import_issues_set_updated_at",
    ) not in triggers


async def test_supabase_auth_trigger_is_absent_without_auth_schema(
    database: asyncpg.Connection,
) -> None:
    names = await database.fetch(
        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal ORDER BY tgname"
    )
    assert "on_auth_user_created" not in [str(r["tgname"]) for r in names]
