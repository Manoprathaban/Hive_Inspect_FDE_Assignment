"""Health check route."""

from __future__ import annotations

from fastapi import APIRouter

__all__ = ["router"]

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by Render and CI."""
    return {"status": "ok"}