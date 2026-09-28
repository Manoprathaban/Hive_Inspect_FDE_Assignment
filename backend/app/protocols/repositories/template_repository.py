"""The ``TemplateRepository`` protocol boundary.

Persistence boundary for templates and their import issues. A PostgreSQL adapter and an
in-memory/fake adapter (tests) both satisfy this contract. Methods are async because
PostgreSQL wiring is async, and every method takes the acting ``owner_id`` so the contract
explicitly carries the authorization scoping the adapter must enforce (RLS is defense in
depth; the repository never trusts the caller).
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from app.domain.models.template import ImportIssue, Template, TemplateSummary

__all__ = ["TemplateRepository"]


@runtime_checkable
class TemplateRepository(Protocol):
    """Persistence boundary for templates.

    All ``template_id``-/``owner_id``-keyed reads, writes, and deletes MUST be scoped to
    ``owner_id``; returning or mutating another user's data is a contract violation.
    """

    async def save(self, template: Template, *, owner_id: uuid.UUID) -> Template:
        """Persist a new template (with sections/items/comments/options/issues) and
        return the saved aggregate with its assigned ``id`` and ``owner_id``."""
        ...

    async def get(self, template_id: uuid.UUID, *, owner_id: uuid.UUID) -> Template | None:
        """Fetch one template with its full ordered hierarchy; ``None`` when missing."""
        ...

    async def list_for_user(self, owner_id: uuid.UUID) -> list[TemplateSummary]:
        """List the acting user's templates (summaries, ordered by ``updated_at``)."""
        ...

    async def update_section_name(
        self,
        *,
        template_id: uuid.UUID,
        section_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
    ) -> None:
        """Rename a section owned by ``owner_id``."""
        ...

    async def update_item_name(
        self,
        *,
        template_id: uuid.UUID,
        item_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str,
    ) -> None:
        """Rename an item owned by ``owner_id``."""
        ...

    async def update_comment_content(
        self,
        *,
        template_id: uuid.UUID,
        comment_id: uuid.UUID,
        owner_id: uuid.UUID,
        content: str,
    ) -> None:
        """Replace a comment's content for a template owned by ``owner_id``."""
        ...

    async def duplicate(
        self,
        template_id: uuid.UUID,
        *,
        owner_id: uuid.UUID,
        new_name: str | None = None,
    ) -> Template:
        """Duplicate a template owned by ``owner_id`` and return the independent copy.

        The copy gets fresh ids for the template and every descendant row; it never shares
        mutable children with the source. ``copied_from_id`` is provenance only.
        """
        ...

    async def delete(self, template_id: uuid.UUID, *, owner_id: uuid.UUID) -> bool:
        """Delete a template (and cascade descendants). ``False`` when not found/owned."""
        ...

    async def list_import_issues(
        self, template_id: uuid.UUID, *, owner_id: uuid.UUID
    ) -> list[ImportIssue]:
        """List a template's import issues, newest first."""
        ...