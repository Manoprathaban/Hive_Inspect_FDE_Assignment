"""The ``AuthenticationProvider`` protocol boundary.

Every provider returns the same domain :class:`~app.domain.models.user.UserContext`, so
application/domain code never knows whether the user came from Supabase Auth or the
development stub. The ``user_id`` in the context is the ownership identity stored as
``templates.owner_id``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.models.user import UserContext

__all__ = ["AuthenticationProvider"]


@runtime_checkable
class AuthenticationProvider(Protocol):
    """Resolve the currently authenticated user."""

    async def get_current_user(self) -> UserContext:
        """Return the authenticated :class:`UserContext`; raise when unauthenticated."""
        ...