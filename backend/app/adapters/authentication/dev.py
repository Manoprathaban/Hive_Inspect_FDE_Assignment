"""Deterministic development authentication stub.

Explicitly dev-only. Resolves every request to the same deterministic user
(the identity seeded by ``database/seed/dev_auth.sql``), so the backend runs fully
offline. It must never be enabled in production: like every provider it returns the same
:class:`UserContext` shape, and it does NOT weaken RLS — locally the backend connects with
a privileged role and enforces ``owner_id`` scoping in the application layer.
"""

from __future__ import annotations

import uuid

from app.domain.models.user import AuthProviderKind, UserContext

__all__ = ["DEV_USER_ID", "DevAuthProvider"]

DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class DevAuthProvider:
    """Always authenticates as the deterministic development user.

    The received token is deliberately ignored (``Authorization`` is required by the API
    layer but its value is meaningless offline — §4 Development).
    """

    async def get_current_user(self, token: str) -> UserContext:
        return UserContext(user_id=DEV_USER_ID, provider=AuthProviderKind.DEV)
