"""Request-scoped dependencies for the template API (FastAPI).

Composition-root wiring: this layer is the only place that binds the concrete adapters
(auth provider, Spectora importer, repository). Nothing below depends on FastAPI or on
these concrete implementations.

The activated auth provider depends on ``Settings.app_env``: ``development`` uses the
deterministic :class:`DevAuthProvider` (the bearer header stays required but its value is
ignored — §4 Development); ``production`` uses :class:`SupabaseAuthProvider`, which
verifies the Supabase access token (fails closed without ``SUPABASE_JWT_SECRET``).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.adapters.authentication.dev import DevAuthProvider
from app.adapters.authentication.supabase import SupabaseAuthProvider
from app.api.errors import ApiError
from app.domain.models.user import UserContext
from app.infrastructure.config.settings import get_settings
from app.protocols.authentication import AuthenticationProvider

__all__ = ["bearer_scheme", "get_auth_provider", "get_current_user"]

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_provider() -> AuthenticationProvider:
    """Return the authentication provider bound at startup by environment.

    ``APP_ENV=production`` activates real Supabase JWT validation; anything else keeps the
    deterministic dev stub. Both satisfy the same :class:`AuthenticationProvider`
    protocol, so routes never change.
    """

    settings = get_settings()
    if settings.app_env == "production":
        return SupabaseAuthProvider(
            jwt_secret=settings.supabase_jwt_secret or "",
            supabase_url=settings.supabase_url,
        )
    return DevAuthProvider()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    provider: Annotated[AuthenticationProvider, Depends(get_auth_provider)],
) -> UserContext:
    """Resolve the authenticated user, mapping failures to the §14 envelope.

    Every contract endpoint (all routes except ``/health``) depends on this. A missing
    ``Authorization`` header is ``401 AUTHENTICATION_REQUIRED``; a provider that rejects the
    credentials is ``401 INVALID_TOKEN``. Both are indistinguishable failures by design.
    """

    if credentials is None:
        raise ApiError(
            401,
            "AUTHENTICATION_REQUIRED",
            "Authentication is required to access this resource.",
        )
    try:
        return await provider.get_current_user(token=credentials.credentials)
    except Exception as exc:
        logger.debug("authentication provider rejected credentials", exc_info=exc)
        raise ApiError(
            401,
            "INVALID_TOKEN",
            "The provided credentials are invalid or expired.",
        ) from exc
