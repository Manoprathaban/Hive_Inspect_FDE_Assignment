"""Request-scoped dependencies for the template API (FastAPI).

Composition-root wiring: this layer is the only place that binds the concrete adapters
(auth provider, Spectora importer, repository). Nothing below depends on FastAPI or on
these concrete implementations.

The activated auth provider depends on ``Settings.app_env``: ``development`` uses
:class:`DevAuthProvider`, which turns the presented credential into an identity (a real
JWT's ``sub``, a ``DEV_AUTH_USERS`` entry, or a stable per-credential id) so two development
logins are never the same tenant; ``production`` uses :class:`SupabaseAuthProvider`, which
verifies the Supabase access token (fails closed without ``SUPABASE_JWT_SECRET``).
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncEngine

from app.adapters.authentication.dev import DevAuthProvider, parse_dev_auth_users
from app.adapters.authentication.supabase import SupabaseAuthProvider
from app.api.errors import ApiError
from app.domain.models.user import UserContext
from app.infrastructure.config.settings import get_settings
from app.infrastructure.database import ensure_user_row, get_async_engine
from app.protocols.authentication import AuthenticationProvider

__all__ = [
    "bearer_scheme",
    "get_auth_provider",
    "get_current_user",
    "get_database_engine",
    "provision_identity",
    "resolve_current_user",
]

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_database_engine() -> AsyncEngine:
    """The application's engine, injected rather than imported so tests can redirect it."""

    return get_async_engine()


def get_auth_provider() -> AuthenticationProvider:
    """Return the authentication provider bound at startup by environment.

    ``APP_ENV=production`` activates real Supabase JWT validation; anything else keeps the
    development provider. Both satisfy the same :class:`AuthenticationProvider` protocol, so
    routes never change.
    """

    settings = get_settings()
    if settings.app_env == "production":
        return SupabaseAuthProvider(
            jwt_secret=settings.supabase_jwt_secret,
            supabase_url=settings.supabase_url,
        )
    return DevAuthProvider(parse_dev_auth_users(settings.dev_auth_users))


async def resolve_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    provider: Annotated[AuthenticationProvider, Depends(get_auth_provider)],
) -> UserContext:
    """Resolve the authenticated user, mapping failures to the §14 envelope.

    A missing ``Authorization`` header is ``401 AUTHENTICATION_REQUIRED``; a provider that
    rejects the credentials is ``401 INVALID_TOKEN``. Both are indistinguishable failures by
    design.
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


async def provision_identity(
    user: Annotated[UserContext, Depends(resolve_current_user)],
    engine: Annotated[AsyncEngine, Depends(get_database_engine)],
) -> UserContext:
    """Give a synthesised development identity its ``public.users`` row, then pass it on.

    Production identities are mirrored in by the ``on_auth_user_created`` trigger, so this is
    a no-op there. A development identity is derived from a credential instead, and every
    write would otherwise fail the ``owner_id`` foreign key.

    This is a separate dependency so tests that stub the repository can replace it without
    also standing up a database, and the engine arrives through ``Depends`` so a test can
    point it at a throwaway one. ``user`` arrives the same way — as a plain parameter,
    FastAPI would try to validate ``UserContext`` as a request body.
    """

    if get_settings().app_env != "production":
        await ensure_user_row(engine, user_id=user.user_id)
    return user


async def get_current_user(
    user: Annotated[UserContext, Depends(provision_identity)],
) -> UserContext:
    """The authenticated user for this request; every contract endpoint depends on this."""

    return user
