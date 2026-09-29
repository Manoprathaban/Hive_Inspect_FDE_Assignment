"""Use case: import a template source.

Depends only on the ``TemplateImporter`` protocol, so the concrete importer (Spectora,
future brand, or mock) is swappable without changing this code. The API layer wraps this
use case; it never sees FastAPI request objects here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.models.template import Template
from app.protocols.importers.template_importer import TemplateImporter

__all__ = ["ImportTemplateUseCase"]


@dataclass(frozen=True)
class ImportTemplateUseCase:
    """Orchestrates a :class:`TemplateImporter` for a raw template source."""

    importer: TemplateImporter

    def execute(self, source: bytes, *, filename: str = "") -> Template:
        """Import ``source`` bytes into a domain :class:`Template`."""
        return self.importer.import_template(source, filename=filename)
