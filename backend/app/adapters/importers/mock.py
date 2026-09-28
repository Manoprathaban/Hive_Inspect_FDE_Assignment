"""Mock importer adapter.

Satisfies the ``TemplateImporter`` protocol for tests and as a reference implementation.
The real Spectora importer is a later phase and will land in this package.
"""

from __future__ import annotations

from app.domain.models.template import Template

__all__ = ["MockTemplateImporter"]


class MockTemplateImporter:
    """Returns a bare :class:`Template` without parsing the source."""

    def import_template(self, source: bytes, *, filename: str = "") -> Template:
        return Template(
            name=filename or "Mock template",
            source="mock",
            source_filename=filename or None,
        )