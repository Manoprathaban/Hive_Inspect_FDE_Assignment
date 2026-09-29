"""PostgreSQL ``TemplateRepository`` adapter (SQLAlchemy async + asyncpg).

Implements :class:`~app.protocols.repositories.template_repository.TemplateRepository`
against the schema in ``database/migrations/0001_create_template_schema.sql`` using raw
SQLAlchemy Core ``text()`` statements that follow the parameterized query patterns in
``docs/DATABASE_DESIGN.md`` §20. No ORM mapping: the statements are the contract, and the
aggregate is assembled from ordered batched reads.

Ownership is enforced in every statement — template rows by ``owner_id`` directly, child
rows by an ``EXISTS`` that walks the parent chain up to the template owner — so a caller
can never read or mutate another user's data even where RLS is not active. Missing **or**
foreign templates and unresolvable child ids raise the same domain exceptions as the
in-memory adapter, keeping the API's §20 error mapping identical; RLS (``0002``) is
defense in depth, never the replacement for these predicates.

Semantics match the in-memory adapter documented at
``app/adapters/repositories/in_memory.py``:

* ``save`` — single transaction persisting the aggregate with new ids for the template
  and every descendant, issues inserted in aggregate order;
* ``get`` — full hierarchy (and issues) or ``None``; a missing/foreign template is
  indistinguishable;
* ``update_*`` — single-row, owner-scoped edits that never bump template timestamps
  (``templates`` is untouched, §21); the template is verified first so the child-specific
  error is only raised once the owned template is proven (§20 mapping);
* ``duplicate`` — one transaction; the copy gets brand-new ids down the whole tree,
  ``copied_from_id`` provenance, its own timestamps, no issues, and
  ``"<source name> (Copy)"`` when no name is given (§17);
* ``list_import_issues`` — newest first (``created_at DESC``, then ``id DESC`` as a
  deterministic tiebreak for equal batch timestamps).

A connection is opened lazily per operation, so constructing/building the app never
connects to Postgres until the first repository call.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

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
    TemplateSummary,
)

__all__ = ["PostgresTemplateRepository"]

_TEMPLATE_COLUMNS = (
    "id, owner_id, name, source, source_filename, copied_from_id, created_at, updated_at"
)
_SECTION_COLUMNS = "id, name, display_order"
_ITEM_COLUMNS = "id, section_id, name, display_order"
_COMMENT_COLUMNS = (
    "id, item_id, name, content, comment_type, category, answer_type, display_order, "
    "recommendation, default_value, default_value_2, default_unit_type, estimate_min, "
    "estimate_max, source_row"
)
_OPTION_COLUMNS = "id, comment_id, option_type, value, display_order"
_ISSUE_COLUMNS = "id, source_row, source_field, issue_type, message, raw_value, severity"


class PostgresTemplateRepository:
    """Owner-scoped template persistence backed by PostgreSQL."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def save(self, template: Template, *, owner_id: uuid.UUID) -> Template:
        """Persist a new aggregate (with sections/items/comments/options/issues)."""

        async with self._engine.begin() as conn:
            template_id, created_at, updated_at = await _insert_template(
                conn,
                owner_id=owner_id,
                name=template.name,
                source=template.source,
                source_filename=template.source_filename,
                copied_from_id=template.copied_from_id,
            )
            saved_sections = await _persist_hierarchy(
                conn, template_id=template_id, sections=template.sections
            )
            saved_issues = await _persist_issues(
                conn, template_id=template_id, issues=template.issues
            )
        return Template(
            id=template_id,
            owner_id=owner_id,
            copied_from_id=template.copied_from_id,
            created_at=created_at,
            updated_at=updated_at,
            name=template.name,
            source=template.source,
            source_filename=template.source_filename,
            sections=saved_sections,
            issues=saved_issues,
        )

    async def duplicate(
        self,
        template_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        new_name: str | None = None,
    ) -> Template:
        """Create an independent deep copy (provenance, new ids, no issues)."""

        async with self._engine.begin() as conn:
            source = await _load_template(
                conn,
                template_id=template_id,
                owner_id=owner_id,
                include_issues=False,
            )
            if source is None:
                raise TemplateNotFoundError(template_id)
            name = new_name if new_name is not None else f"{source.name} (Copy)"
            copy_id, created_at, updated_at = await _insert_template(
                conn,
                owner_id=owner_id,
                name=name,
                source=source.source,
                source_filename=source.source_filename,
                copied_from_id=template_id,
            )
            copied_sections = await _persist_hierarchy(
                conn, template_id=copy_id, sections=source.sections
            )
        return Template(
            id=copy_id,
            owner_id=owner_id,
            copied_from_id=template_id,
            created_at=created_at,
            updated_at=updated_at,
            name=name,
            source=source.source,
            source_filename=source.source_filename,
            sections=copied_sections,
            issues=[],
        )

    async def update_section_name(
        self,
        *,
        template_id: uuid.UUID,
        section_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
    ) -> None:
        """Rename an owned section (single-row, template timestamps untouched)."""

        async with self._engine.begin() as conn:
            await _check_template_owned(conn, template_id=template_id, owner_id=owner_id)
            result = await conn.execute(
                text(
                    "UPDATE public.sections SET name = :name "
                    "WHERE id = :section_id "
                    "AND EXISTS (SELECT 1 FROM public.templates t "
                    "WHERE t.id = sections.template_id AND t.owner_id = :owner_id)"
                ),
                {"name": name, "section_id": section_id, "owner_id": owner_id},
            )
            if result.rowcount == 0:
                raise SectionNotFoundError(section_id)

    async def update_item_name(
        self,
        *,
        template_id: uuid.UUID,
        item_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
    ) -> None:
        """Rename an owned item (single-row, template timestamps untouched)."""

        async with self._engine.begin() as conn:
            await _check_template_owned(conn, template_id=template_id, owner_id=owner_id)
            result = await conn.execute(
                text(
                    "UPDATE public.items SET name = :name "
                    "WHERE id = :item_id "
                    "AND EXISTS (SELECT 1 FROM public.sections s "
                    "JOIN public.templates t ON t.id = s.template_id "
                    "WHERE s.id = items.section_id AND t.owner_id = :owner_id)"
                ),
                {"name": name, "item_id": item_id, "owner_id": owner_id},
            )
            if result.rowcount == 0:
                raise ItemNotFoundError(item_id)

    async def update_comment_content(
        self,
        *,
        template_id: uuid.UUID,
        comment_id: uuid.UUID,
        owner_id: uuid.UUID,
        content: str,
    ) -> None:
        """Replace an owned comment's content (single-row edit, verbatim)."""

        async with self._engine.begin() as conn:
            await _check_template_owned(conn, template_id=template_id, owner_id=owner_id)
            result = await conn.execute(
                text(
                    "UPDATE public.comments SET content = :content "
                    "WHERE id = :comment_id "
                    "AND EXISTS (SELECT 1 FROM public.items i "
                    "JOIN public.sections s ON s.id = i.section_id "
                    "JOIN public.templates t ON t.id = s.template_id "
                    "WHERE i.id = comments.item_id AND t.owner_id = :owner_id)"
                ),
                {"content": content, "comment_id": comment_id, "owner_id": owner_id},
            )
            if result.rowcount == 0:
                raise CommentNotFoundError(comment_id)

    async def delete(self, template_id: uuid.UUID, *, owner_id: uuid.UUID) -> bool:
        """Delete an owned template and its descendants; ``False`` when not owned."""

        async with self._engine.begin() as conn:
            result = await conn.execute(
                text(
                    "DELETE FROM public.templates WHERE id = :template_id AND owner_id = :owner_id"
                ),
                {"template_id": template_id, "owner_id": owner_id},
            )
            return result.rowcount > 0

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get(self, template_id: uuid.UUID, *, owner_id: uuid.UUID) -> Template | None:
        """Full hierarchy of an owned template; ``None`` when missing/foreign."""

        async with self._engine.connect() as conn:
            return await _load_template(
                conn,
                template_id=template_id,
                owner_id=owner_id,
                include_issues=True,
            )

    async def list_for_user(self, owner_id: uuid.UUID) -> list[TemplateSummary]:
        """Summaries of the acting user's templates, most recently updated first."""

        async with self._engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, name, source, source_filename, created_at, updated_at "
                        "FROM public.templates WHERE owner_id = :owner_id "
                        "ORDER BY updated_at DESC, id DESC"
                    ),
                    {"owner_id": owner_id},
                )
            ).all()
        return [
            TemplateSummary(
                id=row.id,
                name=row.name,
                source=row.source,
                source_filename=row.source_filename,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]

    async def list_import_issues(
        self, template_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> list[ImportIssue]:
        """An owned template's import issues, newest first; ``[]`` when missing/foreign."""

        async with self._engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT " + _ISSUE_COLUMNS + " "
                        "FROM public.import_issues "
                        "WHERE template_id = :template_id "
                        "AND EXISTS (SELECT 1 FROM public.templates t "
                        "WHERE t.id = import_issues.template_id "
                        "AND t.owner_id = :owner_id) "
                        "ORDER BY created_at DESC, id DESC"
                    ),
                    {"template_id": template_id, "owner_id": owner_id},
                )
            ).all()
        return [
            ImportIssue(
                id=row.id,
                source_row=row.source_row,
                source_field=row.source_field,
                issue_type=IssueType(row.issue_type),
                message=row.message,
                raw_value=row.raw_value,
                severity=IssueSeverity(row.severity),
            )
            for row in rows
        ]


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------


async def _check_template_owned(
    conn: AsyncConnection, *, template_id: uuid.UUID, owner_id: uuid.UUID
) -> None:
    """Raise ``TemplateNotFoundError`` unless the template exists for ``owner_id``.

    Missing and foreign are deliberately the same failure (§20).
    """

    row = (
        await conn.execute(
            text("SELECT 1 FROM public.templates WHERE id = :template_id AND owner_id = :owner_id"),
            {"template_id": template_id, "owner_id": owner_id},
        )
    ).first()
    if row is None:
        raise TemplateNotFoundError(template_id)


async def _insert_template(
    conn: AsyncConnection,
    *,
    owner_id: uuid.UUID,
    name: str,
    source: str,
    source_filename: str | None,
    copied_from_id: uuid.UUID | None,
) -> tuple[uuid.UUID, Any, Any]:
    """Insert a ``templates`` row and return ``(id, created_at, updated_at)``."""

    row = (
        await conn.execute(
            text(
                "INSERT INTO public.templates "
                "(owner_id, name, source, source_filename, copied_from_id) "
                "VALUES (:owner_id, :name, :source, :source_filename, :copied_from_id) "
                "RETURNING id, created_at, updated_at"
            ),
            {
                "owner_id": owner_id,
                "name": name,
                "source": source,
                "source_filename": source_filename,
                "copied_from_id": copied_from_id,
            },
        )
    ).one()
    return row.id, row.created_at, row.updated_at


async def _persist_hierarchy(
    conn: AsyncConnection, *, template_id: uuid.UUID, sections: list[Section]
) -> list[Section]:
    """Insert deep copies of ``sections`` (with their items/comments/options) under
    ``template_id``, returning them with their brand-new ids."""

    saved_sections: list[Section] = []
    for section in sections:
        section_row = (
            await conn.execute(
                text(
                    "INSERT INTO public.sections (template_id, name, display_order) "
                    "VALUES (:template_id, :name, :display_order) RETURNING id"
                ),
                {
                    "template_id": template_id,
                    "name": section.name,
                    "display_order": section.display_order,
                },
            )
        ).one()
        saved_items: list[Item] = []
        for item in section.items:
            item_row = (
                await conn.execute(
                    text(
                        "INSERT INTO public.items (section_id, name, display_order) "
                        "VALUES (:section_id, :name, :display_order) RETURNING id"
                    ),
                    {
                        "section_id": section_row.id,
                        "name": item.name,
                        "display_order": item.display_order,
                    },
                )
            ).one()
            saved_comments: list[Comment] = []
            for comment in item.comments:
                comment_row = (
                    await conn.execute(
                        text(
                            "INSERT INTO public.comments "
                            "(item_id, name, content, comment_type, category, "
                            "answer_type, display_order, recommendation, default_value, "
                            "default_value_2, default_unit_type, estimate_min, estimate_max, "
                            "source_row) "
                            "VALUES (:item_id, :name, :content, :comment_type, :category, "
                            ":answer_type, :display_order, :recommendation, :default_value, "
                            ":default_value_2, :default_unit_type, :estimate_min, :estimate_max, "
                            ":source_row) "
                            "RETURNING id"
                        ),
                        {
                            "item_id": item_row.id,
                            "name": comment.name,
                            "content": comment.content,
                            "comment_type": comment.comment_type.value,
                            "category": comment.category,
                            "answer_type": comment.answer_type.value,
                            "display_order": comment.display_order,
                            "recommendation": comment.recommendation,
                            "default_value": comment.default_value,
                            "default_value_2": comment.default_value_2,
                            "default_unit_type": comment.default_unit_type,
                            "estimate_min": comment.estimate_min,
                            "estimate_max": comment.estimate_max,
                            "source_row": comment.source_row,
                        },
                    )
                ).one()
                saved_options: list[CommentOption] = []
                for option in comment.options:
                    option_row = (
                        await conn.execute(
                            text(
                                "INSERT INTO public.comment_options "
                                "(comment_id, option_type, value, display_order) "
                                "VALUES (:comment_id, :option_type, :value, :display_order) "
                                "RETURNING id"
                            ),
                            {
                                "comment_id": comment_row.id,
                                "option_type": option.option_type.value,
                                "value": option.value,
                                "display_order": option.display_order,
                            },
                        )
                    ).one()
                    saved_options.append(
                        CommentOption(
                            id=option_row.id,
                            option_type=option.option_type,
                            value=option.value,
                            display_order=option.display_order,
                        )
                    )
                saved_comments.append(
                    Comment(
                        id=comment_row.id,
                        name=comment.name,
                        content=comment.content,
                        comment_type=comment.comment_type,
                        answer_type=comment.answer_type,
                        display_order=comment.display_order,
                        category=comment.category,
                        recommendation=comment.recommendation,
                        default_value=comment.default_value,
                        default_value_2=comment.default_value_2,
                        default_unit_type=comment.default_unit_type,
                        estimate_min=comment.estimate_min,
                        estimate_max=comment.estimate_max,
                        source_row=comment.source_row,
                        options=saved_options,
                    )
                )
            saved_items.append(
                Item(
                    id=item_row.id,
                    name=item.name,
                    display_order=item.display_order,
                    comments=saved_comments,
                )
            )
        saved_sections.append(
            Section(
                id=section_row.id,
                name=section.name,
                display_order=section.display_order,
                items=saved_items,
            )
        )
    return saved_sections


async def _persist_issues(
    conn: AsyncConnection, *, template_id: uuid.UUID, issues: list[ImportIssue]
) -> list[ImportIssue]:
    """Insert ``issues`` in aggregate order and return them with their new ids."""

    saved: list[ImportIssue] = []
    for issue in issues:
        row = (
            await conn.execute(
                text(
                    "INSERT INTO public.import_issues "
                    "(template_id, source_row, source_field, issue_type, message, raw_value, "
                    "severity) "
                    "VALUES (:template_id, :source_row, :source_field, :issue_type, "
                    ":message, :raw_value, :severity) "
                    "RETURNING id"
                ),
                {
                    "template_id": template_id,
                    "source_row": issue.source_row,
                    "source_field": issue.source_field,
                    "issue_type": issue.issue_type.value,
                    "message": issue.message,
                    "raw_value": issue.raw_value,
                    "severity": issue.severity.value,
                },
            )
        ).one()
        saved.append(
            ImportIssue(
                id=row.id,
                source_row=issue.source_row,
                source_field=issue.source_field,
                issue_type=issue.issue_type,
                message=issue.message,
                raw_value=issue.raw_value,
                severity=issue.severity,
            )
        )
    return saved


async def _load_template(
    conn: AsyncConnection,
    *,
    template_id: uuid.UUID,
    owner_id: uuid.UUID,
    include_issues: bool,
) -> Template | None:
    """Assemble an owned template's full hierarchy (and issues when requested).

    Batched, ordered reads (§20 pattern 3). Child columns referenced by the ordering must
    be selected, so the child queries select slightly more than the aggregated shape.
    """

    template_row = (
        await conn.execute(
            text(
                "SELECT " + _TEMPLATE_COLUMNS + " "
                "FROM public.templates WHERE id = :template_id AND owner_id = :owner_id"
            ),
            {"template_id": template_id, "owner_id": owner_id},
        )
    ).first()
    if template_row is None:
        return None

    section_rows = (
        await conn.execute(
            text(
                "SELECT " + _SECTION_COLUMNS + " "
                "FROM public.sections WHERE template_id = :template_id "
                "ORDER BY display_order"
            ),
            {"template_id": template_id},
        )
    ).all()

    section_ids = [row.id for row in section_rows]
    item_rows = []
    if section_ids:
        item_rows = (
            await conn.execute(
                text(
                    "SELECT " + _ITEM_COLUMNS + " "
                    "FROM public.items WHERE section_id IN :section_ids "
                    "ORDER BY section_id, display_order"
                ).bindparams(bindparam("section_ids", expanding=True)),
                {"section_ids": section_ids},
            )
        ).all()

    item_ids = [row.id for row in item_rows]
    comment_rows = []
    if item_ids:
        comment_rows = (
            await conn.execute(
                text(
                    "SELECT " + _COMMENT_COLUMNS + " "
                    "FROM public.comments WHERE item_id IN :item_ids "
                    "ORDER BY item_id, display_order, id"
                ).bindparams(bindparam("item_ids", expanding=True)),
                {"item_ids": item_ids},
            )
        ).all()

    comment_ids = [row.id for row in comment_rows]
    option_rows = []
    if comment_ids:
        option_rows = (
            await conn.execute(
                text(
                    "SELECT " + _OPTION_COLUMNS + " "
                    "FROM public.comment_options WHERE comment_id IN :comment_ids "
                    "ORDER BY comment_id, display_order"
                ).bindparams(bindparam("comment_ids", expanding=True)),
                {"comment_ids": comment_ids},
            )
        ).all()

    issues: list[ImportIssue] = []
    if include_issues:
        issue_rows = (
            await conn.execute(
                text(
                    "SELECT " + _ISSUE_COLUMNS + " "
                    "FROM public.import_issues "
                    "WHERE template_id = :template_id "
                    "AND EXISTS (SELECT 1 FROM public.templates t "
                    "WHERE t.id = import_issues.template_id AND t.owner_id = :owner_id) "
                    "ORDER BY created_at DESC, id DESC"
                ),
                {"template_id": template_id, "owner_id": owner_id},
            )
        ).all()
        issues = [
            ImportIssue(
                id=row.id,
                source_row=row.source_row,
                source_field=row.source_field,
                issue_type=IssueType(row.issue_type),
                message=row.message,
                raw_value=row.raw_value,
                severity=IssueSeverity(row.severity),
            )
            for row in issue_rows
        ]

    options_by_comment: dict[uuid.UUID, list[CommentOption]] = {
        comment_id: [] for comment_id in comment_ids
    }
    for option_row in option_rows:
        options_by_comment.setdefault(option_row.comment_id, []).append(
            CommentOption(
                id=option_row.id,
                option_type=OptionType(option_row.option_type),
                value=option_row.value,
                display_order=option_row.display_order,
            )
        )

    comments_by_item: dict[uuid.UUID, list[Comment]] = {item_id: [] for item_id in item_ids}
    for comment_row in comment_rows:
        comments_by_item.setdefault(comment_row.item_id, []).append(
            Comment(
                id=comment_row.id,
                name=comment_row.name,
                content=comment_row.content,
                comment_type=CommentType(comment_row.comment_type),
                answer_type=AnswerType(comment_row.answer_type),
                display_order=comment_row.display_order,
                category=comment_row.category,
                recommendation=comment_row.recommendation,
                default_value=comment_row.default_value,
                default_value_2=comment_row.default_value_2,
                default_unit_type=comment_row.default_unit_type,
                estimate_min=comment_row.estimate_min,
                estimate_max=comment_row.estimate_max,
                source_row=comment_row.source_row,
                options=options_by_comment.get(comment_row.id, []),
            )
        )

    items_by_section: dict[uuid.UUID, list[Item]] = {section_id: [] for section_id in section_ids}
    for item_row in item_rows:
        items_by_section.setdefault(item_row.section_id, []).append(
            Item(
                id=item_row.id,
                name=item_row.name,
                display_order=item_row.display_order,
                comments=comments_by_item.get(item_row.id, []),
            )
        )

    sections = [
        Section(
            id=section_row.id,
            name=section_row.name,
            display_order=section_row.display_order,
            items=items_by_section.get(section_row.id, []),
        )
        for section_row in section_rows
    ]

    return Template(
        id=template_row.id,
        owner_id=owner_id,
        copied_from_id=template_row.copied_from_id,
        created_at=template_row.created_at,
        updated_at=template_row.updated_at,
        name=template_row.name,
        source=template_row.source,
        source_filename=template_row.source_filename,
        sections=sections,
        issues=issues,
    )
