"""Dependency providers bound at the composition root (FastAPI).

The API layer wires the concrete adapters here — and only here — so routes stay thin:
import -> use case -> save. Swapping the importer or the persistence backend for a later
phase is a change in this module (plus a test override), not in the routes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.adapters.importers.spectora_xlsx import SpectoraXlsxImporter
from app.adapters.repositories.in_memory import InMemoryTemplateRepository
from app.application.use_cases.import_template import ImportTemplateUseCase
from app.protocols.importers.template_importer import TemplateImporter
from app.protocols.repositories.template_repository import TemplateRepository

__all__ = [
    "get_import_template_use_case",
    "get_template_importer",
    "get_template_repository",
]

_repository = InMemoryTemplateRepository()


def get_template_importer() -> TemplateImporter:
    """Return the source-specific importer bound at startup."""

    return SpectoraXlsxImporter()


def get_import_template_use_case(
    importer: Annotated[TemplateImporter, Depends(get_template_importer)],
) -> ImportTemplateUseCase:
    """Compose the import use case with its importer dependency."""

    return ImportTemplateUseCase(importer=importer)


def get_template_repository() -> TemplateRepository:
    """Return the persistence adapter bound at startup.

    A single in-memory instance is shared app-wide (state is process-local); the Postgres
    adapter replaces it without touching the routes.
    """

    return _repository