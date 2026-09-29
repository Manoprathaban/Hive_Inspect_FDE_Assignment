"""HTTP routing (FastAPI).

Routes are thin: parse requests, delegate to use cases, return responses. They do not
contain business logic.

Contract endpoints (``docs/API-CONTRACTS.md``) live under the ``/api`` base path and are
mounted with that prefix in :func:`app.main.create_app`. ``/health`` stays at the root
outside ``/api``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.templates import (
    import_guard_router,
)
from app.api.routes.templates import (
    router as templates_router,
)

__all__ = ["api_router"]

api_router = APIRouter()
api_router.include_router(import_guard_router)
api_router.include_router(templates_router)