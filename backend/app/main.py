"""FastAPI application entry point.

Only the presentation layer is wired here. Application/domain/protocol code stays
framework-agnostic; adapters/infrastructure provide concrete wiring.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.routes import api_router
from app.api.routes.health import router as health_router
from app.infrastructure.config.settings import get_cors_origins, get_settings
from app.infrastructure.logging import configure_logging

__all__ = ["app", "create_app"]


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging()

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=get_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(application)
    application.include_router(api_router, prefix="/api")
    application.include_router(health_router)
    return application


app = create_app()