"""The ``TemplateImporter`` protocol boundary.

Converts a template source (bytes of an XLSX/XML worksheet, e.g. a Spectora export) into
the domain :class:`TemplateImport`. Application code depends on this protocol — never on
any concrete importer.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models.template import TemplateImport

__all__ = ["TemplateImporter"]


@runtime_checkable
class TemplateImporter(Protocol):
    """Import a template source into a domain :class:`TemplateImport`."""

    def import_template(self, source: bytes, *, filename: str = "") -> TemplateImport:
        """Parse ``source`` into a :class:`TemplateImport`.

        Implementations may raise :class:`TemplateImportError` (in
        ``app.domain.exceptions``) when the source cannot be understood. ``filename`` is
        carried through for source attribution only.
        """
        ...