"""The ``TemplateRepository`` protocol boundary.

Persistence boundary for templates. A Supabase-backed adapter and an in-memory adapter can
both satisfy this contract. Repository methods are async because PostgreSQL wiring will be
async.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models.template import TemplateImport

__all__ = ["TemplateRepository"]


@runtime_checkable
class TemplateRepository(Protocol):
    """Persistence boundary for templates."""

    async def save(self, template: TemplateImport) -> str:
        """Persist a template and return its stable identifier."""
        ...

    async def get(self, template_id: str) -> TemplateImport | None:
        """Fetch a template by identifier; return ``None`` when missing."""
        ...