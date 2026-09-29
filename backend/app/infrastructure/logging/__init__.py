"""Logging configuration for the application.

Configured at startup (see ``app.main``). Adapts to ``debug``/``app_env``.
"""

from __future__ import annotations

import logging

from app.infrastructure.config.settings import get_settings

__all__ = ["configure_logging"]


def configure_logging() -> None:
    """Install the root ``logging`` configuration for the service."""
    settings = get_settings()
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("uvicorn").setLevel(level)
