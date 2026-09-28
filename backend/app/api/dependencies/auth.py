"""Request-scoped dependencies for the template API (FastAPI).

Composition-root wiring: this layer is the only place that binds the concrete adapters
(dev auth, Spectora importer, in-memory repository). Nothing below depends on FastAPI or
on these concrete implementations.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.adapters.authentication.dev import DevAuthProvider
from app.api.errors import ApiError
from app.domain.models.user import UserContext
from app.protocols.authentication import AuthenticationProvider

__all__ = ["bearer_scheme", "get_current_user"]

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_provider() -> AuthenticationProvider:
    """Return the authentication provider bound at startup.

    Composition root. Development runs offline against :class:`DevAuthProvider`; the
    production phase swaps in the Supabase token-validating provider behind the same
    :class:`AuthenticationProvider` protocol.
    """

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
        return await provider.get_current_user()
    except Exception as exc:
        logger.debug("authentication provider rejected credentials", exc_info=exc)
        raise ApiError(
            401,
            "INVALID_TOKEN",
            "The provided credentials are invalid or expired.",
        ) from exc