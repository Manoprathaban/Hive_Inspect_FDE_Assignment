"""In-memory ``TemplateRepository`` adapter.

Test/development persistence for the template API before the Postgres adapter lands. An
instance implements the :class:`~app.protocols.repositories.template_repository
.TemplateRepository` shape for the read+write paths the API needs:

* ``save`` — persists a new aggregate and returns it with real assigned UUIDs for the
  template and every descendant (sections/items/comments/options/issues), plus
  ``owner_id`` and ``created_at``/``updated_at``. Issues are persisted with the template
  (import issues never appear without their template).
* ``get`` / ``list_for_user`` / ``list_import_issues`` — owner-scoped reads. ``list_import_issues``
  returns issues newest-first; every issue in an import batch shares a timestamp, so the
  newest-first order is the reverse of aggregate insertion order (deterministic tiebreak,
  matching the Postgres ``ORDER BY created_at DESC``).
* ``update_section_name`` / ``update_item_name`` / ``update_comment_content`` —
  owner-scoped, single-row edits scoped to the given template; a missing **or** foreign
  template raises :class:`~app.domain.exceptions.TemplateNotFoundError` and an unresolvable
  child id raises the child-specific error (``SectionNotFoundError``/``ItemNotFoundError``/
  ``CommentNotFoundError``), mirroring the §20/§17 contract mapping. Template-level
  timestamps are not bumped: edits are single-row updates (§21).
* ``duplicate`` — transactional-feeling deep copy with brand-new ids for the copy and every
  descendant, ``copied_from_id`` pointing at the source (provenance only), its own
  timestamps, no import issues, and ``"<source name> (Copy)"`` as the default name (§17).

``delete`` is not exposed by the API contract, so it raises :class:`NotImplementedError`
to fail loudly rather than silently no-op. State is process-local and non-durable: it
exists so the API can be exercised offline, never as a production store.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from app.domain.exceptions import (
    CommentNotFoundError,
    ItemNotFoundError,
    SectionNotFoundError,
    TemplateNotFoundError,
)
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

    def _owned(self, template_id: uuid.UUID, owner_id: uuid.UUID) -> Template:
        """Return the stored template or raise the generic not-found error.

        Missing and foreign are the same failure (§20): an attacker can never distinguish
        "exists but not yours" from "does not exist".
        """

        template = self._templates.get(template_id)
        if template is None or template.owner_id != owner_id:
            raise TemplateNotFoundError(template_id)
        return template

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
        """Rename a section owned by ``owner_id`` in ``template_id`` (single-row edit)."""

        template = self._owned(template_id, owner_id)
        if not any(section.id == section_id for section in template.sections):
            raise SectionNotFoundError(section_id)
        self._templates[template_id] = _clone(
            replace(
                template,
                sections=[
                    replace(section, name=name) if section.id == section_id else section
                    for section in template.sections
                ],
            )
        )

    async def update_item_name(
        self,
        *,
        template_id: uuid.UUID,
        item_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
    ) -> None:
        """Rename an item owned by ``owner_id`` in ``template_id`` (single-row edit)."""

        template = self._owned(template_id, owner_id)
        if not any(
            item.id == item_id
            for section in template.sections
            for item in section.items
        ):
            raise ItemNotFoundError(item_id)
        sections = [
            replace(
                section,
                items=[
                    replace(item, name=name) if item.id == item_id else item
                    for item in section.items
                ],
            )
            for section in template.sections
        ]
        self._templates[template_id] = _clone(replace(template, sections=sections))

    async def update_comment_content(
        self,
        *,
        template_id: uuid.UUID,
        comment_id: uuid.UUID,
        owner_id: uuid.UUID,
        content: str,
    ) -> None:
        """Replace a comment's content within ``template_id`` (single-row edit)."""

        template = self._owned(template_id, owner_id)
        found = any(
            comment.id == comment_id
            for section in template.sections
            for item in section.items
            for comment in item.comments
        )
        if not found:
            raise CommentNotFoundError(comment_id)
        sections = [
            replace(
                section,
                items=[
                    replace(
                        item,
                        comments=[
                            replace(comment, content=content)
                            if comment.id == comment_id
                            else comment
                            for comment in item.comments
                        ],
                    )
                    for item in section.items
                ],
            )
            for section in template.sections
        ]
        self._templates[template_id] = _clone(replace(template, sections=sections))

    async def duplicate(
        self,
        template_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        new_name: str | None = None,
    ) -> Template:
        """Create an independent deep copy of an owned template (§17).

        The copy gets brand-new ids for the template and every descendant, its own
        timestamps, ``copied_from_id`` = the source id (provenance only), no import issues,
        and ``"<source name> (Copy)"`` when ``new_name`` is omitted.
        """

        template = self._owned(template_id, owner_id)
        now = datetime.now(UTC)
        name = new_name if new_name is not None else f"{template.name} (Copy)"
        copy = _materialize(
            replace(
                template,
                name=name,
                copied_from_id=template.id,
                issues=[],
            ),
            owner_id=owner_id,
            now=now,
        )
        self._templates[copy.id] = _clone(copy)
        return _clone(copy)

    async def delete(self, template_id: uuid.UUID, *, owner_id: uuid.UUID) -> bool:
        raise NotImplementedError("deletion is not exposed by the API contract")