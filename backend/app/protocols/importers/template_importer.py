"""The ``TemplateImporter`` protocol boundary.

Converts a template source (bytes of an XLSX/XML worksheet, e.g. a Spectora export) into
the domain :class:`~app.domain.models.template.Template` aggregate. Application code
depends on this protocol — never on any concrete importer.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models.template import Template

__all__ = ["TemplateImporter"]


@runtime_checkable
class TemplateImporter(Protocol):
    """Import a template source into a domain :class:`Template`."""

    def import_template(self, source: bytes, *, filename: str = "") -> Template:
        """Parse ``source`` into a :class:`Template`.

        Implementations may raise :class:`TemplateImportError` (in
        ``app.domain.exceptions``) when the source cannot be understood. ``filename`` is
        carried through for source attribution only. Unsupported or missing export
        content is reported through the returned template's ``issues`` list rather than
        being silently dropped.
        """
        ...
