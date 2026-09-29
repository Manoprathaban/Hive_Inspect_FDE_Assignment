"""Dependency providers bound at the composition root (FastAPI).

The API layer wires the concrete adapters here — and only here — so routes stay thin:
import -> use case -> save. Swapping the importer or the persistence backend for a later
phase is a change in this module (plus a test override), not in the routes.

Persistence is PostgreSQL by default: the ``PostgresTemplateRepository`` is built from
``Settings.database_url`` and shares one process-wide async engine (see
``app.infrastructure.database``). The in-memory adapter remains available to tests, which
override ``get_template_repository`` per test; routes never know which adapter they use.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.adapters.importers.spectora_xlsx import SpectoraXlsxImporter
from app.adapters.repositories.postgres import PostgresTemplateRepository
from app.application.use_cases.import_template import ImportTemplateUseCase
from app.infrastructure.database import get_async_engine
from app.protocols.importers.template_importer import TemplateImporter
from app.protocols.repositories.template_repository import TemplateRepository

__all__ = [
    "get_import_template_use_case",
    "get_template_importer",
    "get_template_repository",
]

_repository = PostgresTemplateRepository(get_async_engine())


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

    A single Postgres-backed instance is shared app-wide; constructing it never opens a
    connection (SQLAlchemy connects lazily on first repository call). Tests override this
    dependency with an in-memory repository when they need offline state.
    """

    return _repository
