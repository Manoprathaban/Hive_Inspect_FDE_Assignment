"""HTTP routing (FastAPI).

Routes are thin: parse requests, delegate to use cases, return responses. They do not
contain business logic.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.health import router as health_router

__all__ = ["api_router"]

api_router = APIRouter()
api_router.include_router(health_router)