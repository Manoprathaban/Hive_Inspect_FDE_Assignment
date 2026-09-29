"""The ``AuthenticationProvider`` protocol boundary.

Every provider returns the same domain :class:`~app.domain.models.user.UserContext`, so
application/domain code never knows whether the user came from Supabase Auth or the
development stub. The ``user_id`` in the context is the ownership identity stored as
``templates.owner_id``.

Providers receive the raw bearer token (scheme already stripped by the API layer).
:class:`~app.adapters.authentication.dev.DevAuthProvider` ignores it by design; the
production provider validates it against Supabase Auth. Dropping the token from the
boundary keeps the schema clean: an ``owner_id`` is never taken from a client-supplied
claim — it always comes from a token that the activated provider attested.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models.user import UserContext

__all__ = ["AuthenticationProvider"]


@runtime_checkable
class AuthenticationProvider(Protocol):
    """Resolve the currently authenticated user from a bearer token."""

    async def get_current_user(self, token: str) -> UserContext:
        """Return the authenticated :class:`UserContext` for ``token``; raise otherwise."""
        ...
