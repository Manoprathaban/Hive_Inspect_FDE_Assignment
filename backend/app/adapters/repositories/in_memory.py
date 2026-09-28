"""In-memory ``TemplateRepository`` adapter.

Test/development persistence for the template API before the Postgres adapter lands. An
instance implements the :class:`~app.protocols.repositories.template_repository
.TemplateRepository` shape for the read+write paths the current API phase needs:

* ``save`` — persists a new aggregate and returns it with real assigned UUIDs for the
  template and every descendant (sections/items/comments/options/issues), plus
  ``owner_id`` and ``created_at``/``updated_at``. Issues are persisted with the template
  (import issues never appear without their template).
* ``get`` / ``list_for_user`` / ``list_import_issues`` — owner-scoped reads. ``list_import_issues``
  returns issues newest-first; every issue in an import batch shares a timestamp, so the
  newest-first order is the reverse of aggregate insertion order (deterministic tiebreak,
  matching the Postgres ``ORDER BY created_at DESC``).

Mutation methods that later in-memory/Postgres phases will provide
(``update_section_name``, ``update_item_name``, ``update_comment_content``, ``duplicate``,
``delete``) raise :class:`NotImplementedError` so a missing capability fails loudly instead
of silently becoming a no-op. State is process-local and non-durable: it exists so the API
can be exercised offline, never as a production store.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from app.domain.models.template import (
    Comment,
    CommentOption,
    ImportIssue,
    Item,
    Section,
    Template,
    TemplateSummary,
)

__all__ = ["InMemoryTemplateRepository"]


def _clone(template: Template) -> Template:
    """Rebuild ``template`` with the same ids but independent, mutable-safe lists."""

    sections = [
        Section(
            name=section.name,
            display_order=section.display_order,
            id=section.id,
            items=[
                Item(
                    name=item.name,
                    display_order=item.display_order,
                    id=item.id,
                    comments=[
                        Comment(
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
                            options=[
                                CommentOption(
                                    option_type=option.option_type,
                                    value=option.value,
                                    display_order=option.display_order,
                                    id=option.id,
                                )
                                for option in comment.options
                            ],
                            id=comment.id,
                        )
                        for comment in item.comments
                    ],
                )
                for item in section.items
            ],
        )
        for section in template.sections
    ]
    issues = [
        ImportIssue(
            message=issue.message,
            issue_type=issue.issue_type,
            severity=issue.severity,
            source_row=issue.source_row,
            source_field=issue.source_field,
            raw_value=issue.raw_value,
            id=issue.id,
        )
        for issue in template.issues
    ]
    return Template(
        id=template.id,
        owner_id=template.owner_id,
        copied_from_id=template.copied_from_id,
        created_at=template.created_at,
        updated_at=template.updated_at,
        name=template.name,
        source=template.source,
        source_filename=template.source_filename,
        sections=sections,
        issues=issues,
    )


def _materialize(template: Template, *, owner_id: uuid.UUID, now: datetime) -> Template:
    """Fill every unset id and the ownership/timestamps of an aggregate root."""

    sections = []
    for section in template.sections:
        items = []
        for item in section.items:
            comments = []
            for comment in item.comments:
                comments.append(
                    replace(
                        comment,
                        id=uuid.uuid4(),
                        options=[
                            replace(option, id=uuid.uuid4()) for option in comment.options
                        ],
                    )
                )
            items.append(replace(item, id=uuid.uuid4(), comments=comments))
        sections.append(replace(section, id=uuid.uuid4(), items=items))
    return replace(
        template,
        id=uuid.uuid4(),
        owner_id=owner_id,
        copied_from_id=template.copied_from_id,
        created_at=now,
        updated_at=now,
        sections=sections,
        issues=[replace(issue, id=uuid.uuid4()) for issue in template.issues],
    )


class InMemoryTemplateRepository:
    """Owner-scoped, in-process template persistence for tests and dev."""

    def __init__(self) -> None:
        self._templates: dict[uuid.UUID, Template] = {}

    async def save(self, template: Template, *, owner_id: uuid.UUID) -> Template:
        """Persist ``template`` and return it with assigned ids/timestamps."""

        now = datetime.now(UTC)
        saved = _clone(_materialize(template, owner_id=owner_id, now=now))
        self._templates[saved.id] = saved
        return _clone(saved)

    async def get(self, template_id: uuid.UUID, *, owner_id: uuid.UUID) -> Template | None:
        """Return a template owned by ``owner_id``; ``None`` when missing or foreign."""

        template = self._templates.get(template_id)
        if template is None or template.owner_id != owner_id:
            return None
        return _clone(template)

    async def list_for_user(self, owner_id: uuid.UUID) -> list[TemplateSummary]:
        """Summaries of the acting user's templates, most recently updated first."""

        owned = [
            template
            for template in self._templates.values()
            if template.owner_id == owner_id
        ]
        owned.sort(key=lambda template: (template.updated_at, template.id), reverse=True)
        return [
            TemplateSummary(
                id=template.id,
                name=template.name,
                source=template.source,
                source_filename=template.source_filename,
                created_at=template.created_at,
                updated_at=template.updated_at,
            )
            for template in owned
        ]

    async def list_import_issues(
        self, template_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> list[ImportIssue]:
        """A template's import issues, newest first; ``[]`` when missing/foreign."""

        template = self._templates.get(template_id)
        if template is None or template.owner_id != owner_id:
            return []
        return [issue for issue in reversed(template.issues)]

    async def update_section_name(
        self,
        *,
        template_id: uuid.UUID,
        section_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
    ) -> None:
        raise NotImplementedError("section renaming lands with the template editor API")

    async def update_item_name(
        self,
        *,
        template_id: uuid.UUID,
        item_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
    ) -> None:
        raise NotImplementedError("item renaming lands with the template editor API")

    async def update_comment_content(
        self,
        *,
        template_id: uuid.UUID,
        comment_id: uuid.UUID,
        owner_id: uuid.UUID,
        content: str,
    ) -> None:
        raise NotImplementedError("comment editing lands with the template editor API")

    async def duplicate(
        self,
        template_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        new_name: str | None = None,
    ) -> Template:
        raise NotImplementedError("duplication lands with the duplicate API phase")

    async def delete(self, template_id: uuid.UUID, *, owner_id: uuid.UUID) -> bool:
        raise NotImplementedError("deletion is not exposed by the API contract")