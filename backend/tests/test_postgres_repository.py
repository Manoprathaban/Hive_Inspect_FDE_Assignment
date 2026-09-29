"""Live-PostgreSQL tests for the Postgres template repository adapter.

Each test creates a brand-new database, applies the versioned migrations in order, runs
the scenario through the adapter, and drops the database on teardown — mirroring the
``database/tests`` harness (``conftest.py``) so results are deterministic no matter what
state the shared dev database is in.

The suite skips itself when no PostgreSQL server is reachable
(``TEST_DATABASE_ADMIN_URL``; it defaults to the repository's local dev credentials), so
the offline test run and CI's backend job (which has no database service) stay green.
These tests verify the adapter's ``owner_id`` scoping, ordering, single-row edit
semantics, transactional duplicate, and cascade delete against real SQL semantics, plus
an end-to-end round trip of the canonical Spectora export through save/get/duplicate.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.adapters.importers.spectora_xlsx import SpectoraXlsxImporter
from app.adapters.repositories.postgres import PostgresTemplateRepository
from app.domain.exceptions import (
    CommentNotFoundError,
    ItemNotFoundError,
    SectionNotFoundError,
    TemplateNotFoundError,
)
from app.domain.models.template import (
    AnswerType,
    Comment,
    CommentOption,
    CommentType,
    ImportIssue,
    IssueSeverity,
    IssueType,
    Item,
    OptionType,
    Section,
    Template,
)

ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_URL",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "database" / "migrations"
REPO_ROOT = Path(__file__).resolve().parents[2]
USER_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _server_reachable() -> bool:
    """True when a PostgreSQL server accepts the admin DSN."""

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


class _Harness:
    """Throwaway database with migrations applied; dropped on exit."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or f"hi_adapter_{uuid.uuid4().hex[:12]}"
        plain_base = ADMIN_DSN.rsplit("/", 1)[0]
        self._dsn = f"{plain_base}/{self.name}"
        self._engine_url = "postgresql+asyncpg://" + plain_base.split("://", 1)[1] + "/" + self.name

    async def __aenter__(self) -> tuple[AsyncEngine, PostgresTemplateRepository]:
        admin = await asyncpg.connect(ADMIN_DSN)
        try:
            await admin.execute(f'CREATE DATABASE "{self.name}"')
        finally:
            await admin.close()
        try:
            conn = await asyncpg.connect(self._dsn)
            try:
                for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                    await conn.execute(path.read_text(encoding="utf-8"))
                await conn.execute(
                    "INSERT INTO public.users (id) VALUES ($1), ($2)",
                    USER_A,
                    USER_B,
                )
            finally:
                await conn.close()
            self._engine: AsyncEngine = create_async_engine(self._engine_url)
            return self._engine, PostgresTemplateRepository(self._engine)
        except BaseException:
            await self._drop()
            raise

    async def __aexit__(self, *_: object) -> None:
        try:
            await self._engine.dispose()
        finally:
            await self._drop()

    async def _drop(self) -> None:
        admin = await asyncpg.connect(ADMIN_DSN)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{self.name}"')
        finally:
            await admin.close()


def _rich_template(*, name: str = "Sample") -> Template:
    return Template(
        name=name,
        source="spectora",
        source_filename=f"{name.lower()}.xml",
        sections=[
            Section(
                name="Exterior",
                display_order=0,
                items=[
                    Item(
                        name="Roof covering",
                        display_order=0,
                        comments=[
                            Comment(
                                name="General roof covering",
                                content="Inspect <b>tightly</b>.",
                                comment_type=CommentType.DEFECT,
                                answer_type=AnswerType.RANGE,
                                category=1,
                                display_order=0,
                                recommendation="Replace sections.",
                                default_value="Seen",
                                default_value_2="Not seen",
                                default_unit_type="count",
                                estimate_min=Decimal("12.50"),
                                estimate_max=Decimal("99.99"),
                                source_row=3,
                                options=[
                                    CommentOption(
                                        option_type=OptionType.MULTIPLE_CHOICE,
                                        value="Yes",
                                        display_order=0,
                                    ),
                                    CommentOption(
                                        option_type=OptionType.UNIT_TYPE,
                                        value="EA",
                                        display_order=0,
                                    ),
                                ],
                            ),
                            Comment(name="Second", content="", display_order=1),
                        ],
                    )
                ],
            ),
            Section(
                name="Interior",
                display_order=1,
                items=[
                    Item(
                        name="Flooring",
                        display_order=0,
                        comments=[
                            Comment(name="Flooring check", content="text", display_order=0),
                        ],
                    )
                ],
            ),
        ],
        issues=[
            ImportIssue(
                message="first",
                issue_type=IssueType.SOURCE_DATA_MISSING,
                severity=IssueSeverity.WARNING,
            ),
            ImportIssue(
                message="second",
                issue_type=IssueType.UNSUPPORTED_CONTENT,
                severity=IssueSeverity.ERROR,
                source_row=9,
                source_field="Cost to Repair",
                raw_value="garbage",
            ),
        ],
    )


def _collect_ids(template: Template) -> set[uuid.UUID]:
    ids = {template.id}
    for section in template.sections:
        ids.add(section.id)
        for item in section.items:
            ids.add(item.id)
            for comment in item.comments:
                ids.add(comment.id)
                ids.update(option.id for option in comment.options)
    return ids


def test_save_materializes_ids_timestamps_and_full_hierarchy() -> None:
    async def scenario() -> None:
        async with _Harness() as (_engine, repo):
            saved = await repo.save(_rich_template(), owner_id=USER_A)
            assert saved.id is not None
            assert saved.owner_id == USER_A
            assert saved.created_at is not None and saved.updated_at is not None
            assert saved.copied_from_id is None
            assert [issue.message for issue in saved.issues] == ["first", "second"]
            assert all(issue.id is not None for issue in saved.issues)

            section = saved.sections[0]
            assert section.id is not None and section.display_order == 0
            comment = section.items[0].comments[0]
            assert comment.id is not None
            assert comment.estimate_min == Decimal("12.50")
            assert comment.estimate_max == Decimal("99.99")
            assert [option.value for option in comment.options] == ["Yes", "EA"]
            assert [option.option_type for option in comment.options] == [
                OptionType.MULTIPLE_CHOICE,
                OptionType.UNIT_TYPE,
            ]

            loaded = await repo.get(saved.id, owner_id=USER_A)
            assert loaded is not None
            assert loaded.sections[0].items[0].comments[0].content == "Inspect <b>tightly</b>."
            assert {issue.message for issue in loaded.issues} == {"first", "second"}
            assert [s.name for s in loaded.sections] == ["Exterior", "Interior"]

    asyncio.run(scenario())


def test_get_returns_none_for_missing_and_foreign() -> None:
    async def scenario() -> None:
        async with _Harness() as (_engine, repo):
            saved = await repo.save(_rich_template(), owner_id=USER_A)
            assert await repo.get(saved.id, owner_id=USER_A) is not None
            assert await repo.get(saved.id, owner_id=USER_B) is None
            assert await repo.get(uuid.uuid4(), owner_id=USER_A) is None

    asyncio.run(scenario())


def test_list_for_user_is_owner_scoped_and_newest_first() -> None:
    async def scenario() -> None:
        async with _Harness() as (engine, repo):
            first = await repo.save(_rich_template(name="Alpha"), owner_id=USER_A)
            await repo.save(_rich_template(name="Beta"), owner_id=USER_A)
            await repo.save(_rich_template(name="Gamma"), owner_id=USER_B)
            async with engine.begin() as conn:
                await conn.execute(
                    text("ALTER TABLE public.templates " "DISABLE TRIGGER templates_set_updated_at")
                )
                await conn.execute(
                    text("UPDATE public.templates SET updated_at = '2020-01-01' " "WHERE id = :id"),
                    {"id": first.id},
                )
                await conn.execute(
                    text("ALTER TABLE public.templates " "ENABLE TRIGGER templates_set_updated_at")
                )

            summaries = await repo.list_for_user(USER_A)
            assert [summary.name for summary in summaries] == ["Beta", "Alpha"]
            assert [summary.name for summary in await repo.list_for_user(USER_B)] == ["Gamma"]
            assert await repo.list_for_user(uuid.uuid4()) == []

    asyncio.run(scenario())


def test_edits_are_single_row_and_do_not_bump_template_timestamp() -> None:
    async def scenario() -> None:
        async with _Harness() as (_engine, repo):
            saved = await repo.save(_rich_template(), owner_id=USER_A)
            fresh = await repo.get(saved.id, owner_id=USER_A)
            assert fresh is not None
            timestamp = fresh.updated_at

            section_id = saved.sections[0].id
            item_id = saved.sections[0].items[0].id
            comment_id = saved.sections[0].items[0].comments[0].id

            await repo.update_section_name(
                template_id=saved.id,
                section_id=section_id,
                owner_id=USER_A,
                name="Renamed Exterior",
            )
            await repo.update_item_name(
                template_id=saved.id, item_id=item_id, owner_id=USER_A, name="New roof"
            )
            await repo.update_comment_content(
                template_id=saved.id, comment_id=comment_id, owner_id=USER_A, content="Replaced"
            )

            again = await repo.get(saved.id, owner_id=USER_A)
            assert again is not None
            assert again.sections[0].name == "Renamed Exterior"
            assert again.sections[0].items[0].name == "New roof"
            assert again.sections[0].items[0].comments[0].content == "Replaced"
            assert again.sections[1].name == "Interior"
            assert again.updated_at == timestamp

    asyncio.run(scenario())


def test_edits_raise_template_not_found_for_missing_or_foreign() -> None:
    async def scenario() -> None:
        async with _Harness() as (_engine, repo):
            saved = await repo.save(_rich_template(), owner_id=USER_A)
            missing = uuid.uuid4()
            random_child = uuid.uuid4()
            with pytest.raises(TemplateNotFoundError):
                await repo.update_section_name(
                    template_id=saved.id, section_id=random_child, owner_id=USER_B, name="x"
                )
            with pytest.raises(TemplateNotFoundError):
                await repo.update_item_name(
                    template_id=missing, item_id=random_child, owner_id=USER_A, name="x"
                )
            with pytest.raises(TemplateNotFoundError):
                await repo.update_comment_content(
                    template_id=saved.id, comment_id=random_child, owner_id=USER_B, content="x"
                )

    asyncio.run(scenario())


def test_edits_raise_child_specific_not_found_under_owned_template() -> None:
    async def scenario() -> None:
        async with _Harness() as (_engine, repo):
            saved = await repo.save(_rich_template(), owner_id=USER_A)
            missing = uuid.uuid4()
            with pytest.raises(SectionNotFoundError):
                await repo.update_section_name(
                    template_id=saved.id, section_id=missing, owner_id=USER_A, name="x"
                )
            with pytest.raises(ItemNotFoundError):
                await repo.update_item_name(
                    template_id=saved.id, item_id=missing, owner_id=USER_A, name="x"
                )
            with pytest.raises(CommentNotFoundError):
                await repo.update_comment_content(
                    template_id=saved.id, comment_id=missing, owner_id=USER_A, content="x"
                )

    asyncio.run(scenario())


def test_duplicate_creates_independent_deep_copy() -> None:
    async def scenario() -> None:
        async with _Harness() as (_engine, repo):
            saved = await repo.save(_rich_template(name="Porch"), owner_id=USER_A)
            copy = await repo.duplicate(saved.id, owner_id=USER_A)

            assert copy.id != saved.id
            assert copy.copied_from_id == saved.id
            assert copy.name == "Porch (Copy)"
            assert copy.owner_id == USER_A
            assert copy.issues == []
            assert _collect_ids(copy).isdisjoint(_collect_ids(saved))
            assert copy.sections[0].items[0].comments[0].content == (
                saved.sections[0].items[0].comments[0].content
            )

            copy_section_id = copy.sections[0].id
            await repo.update_section_name(
                template_id=copy.id,
                section_id=copy_section_id,
                owner_id=USER_A,
                name="Copy Exterior",
            )
            source_again = await repo.get(saved.id, owner_id=USER_A)
            assert source_again is not None
            assert source_again.sections[0].name == "Exterior"

    asyncio.run(scenario())


def test_duplicate_accepts_custom_name_and_rejects_foreign_source() -> None:
    async def scenario() -> None:
        async with _Harness() as (_engine, repo):
            saved = await repo.save(_rich_template(name="Porch"), owner_id=USER_A)
            copy = await repo.duplicate(saved.id, owner_id=USER_A, new_name="Brand New")
            assert copy.name == "Brand New"
            with pytest.raises(TemplateNotFoundError):
                await repo.duplicate(saved.id, owner_id=USER_B)

    asyncio.run(scenario())


def test_delete_returns_true_owner_scoped_and_cascades() -> None:
    async def scenario() -> None:
        async with _Harness() as (engine, repo):
            saved = await repo.save(_rich_template(), owner_id=USER_A)
            assert await repo.delete(saved.id, owner_id=USER_A) is True
            assert await repo.get(saved.id, owner_id=USER_A) is None
            async with engine.connect() as conn:
                count = (
                    await conn.execute(
                        text("SELECT count(*) FROM public.sections WHERE template_id = :id"),
                        {"id": saved.id},
                    )
                ).scalar_one()
            assert count == 0
            assert await repo.delete(saved.id, owner_id=USER_A) is False

            kept = await repo.save(_rich_template(), owner_id=USER_B)
            assert await repo.delete(kept.id, owner_id=USER_A) is False
            assert await repo.get(kept.id, owner_id=USER_B) is not None

    asyncio.run(scenario())


def test_list_import_issues_newest_first_and_owner_scoped() -> None:
    async def scenario() -> None:
        async with _Harness() as (engine, repo):
            saved = await repo.save(_rich_template(), owner_id=USER_A)
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE public.import_issues SET created_at = now() - interval '5 minutes' "
                        "WHERE message = :m"
                    ),
                    {"m": "first"},
                )
            issues = await repo.list_import_issues(saved.id, owner_id=USER_A)
            assert [issue.message for issue in issues] == ["second", "first"]
            assert await repo.list_import_issues(saved.id, owner_id=USER_B) == []
            assert await repo.list_import_issues(uuid.uuid4(), owner_id=USER_A) == []

    asyncio.run(scenario())


def test_real_spectora_export_round_trips_through_adapter() -> None:
    async def scenario() -> None:
        async with _Harness() as (_engine, repo):
            worksheet = (REPO_ROOT / "sample-data" / "sheet1.xml").read_bytes()
            template = SpectoraXlsxImporter().import_template(worksheet, filename="sheet1.xml")
            saved = await repo.save(template, owner_id=USER_A)
            assert saved.name == "sheet1"
            assert saved.source_filename == "sheet1.xml"

            loaded = await repo.get(saved.id, owner_id=USER_A)
            assert loaded is not None and loaded.sections and loaded.sections[0].items

            copy = await repo.duplicate(saved.id, owner_id=USER_A)
            assert copy.name == "sheet1 (Copy)"
            assert len(copy.sections) == len(loaded.sections)
            assert [len(section.items) for section in copy.sections] == [
                len(section.items) for section in loaded.sections
            ]
            assert sum(
                len(item.comments) for section in copy.sections for item in section.items
            ) == sum(len(item.comments) for section in loaded.sections for item in section.items)

    asyncio.run(scenario())
