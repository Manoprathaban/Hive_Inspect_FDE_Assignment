"""Mock importer adapter.

Satisfies the ``TemplateImporter`` protocol for tests and as a reference implementation.
The real Spectora importer is a later phase and will land in this package.
"""

from __future__ import annotations

from app.domain.models.template import TemplateImport

__all__ = ["MockTemplateImporter"]


class MockTemplateImporter:
    """Returns a bare :class:`TemplateImport` without parsing the source."""

    def import_template(self, source: bytes, *, filename: str = "") -> TemplateImport:
        title = filename or "Mock template"
        return TemplateImport(source_name=filename or "mock", title=title)