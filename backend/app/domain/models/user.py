"""Authenticated user identity shared by every authentication provider.

The application layer only ever sees a :class:`UserContext`, regardless of whether it was
produced by the Supabase Auth adapter (production) or the DevAuthProvider stub
(development). This maps to the identity stored as ``templates.owner_id``.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass

__all__ = ["AuthProviderKind", "UserContext"]


class AuthProviderKind(enum.StrEnum):
    """Stable identifier of the authentication implementation behind a context."""

    SUPABASE_AUTH = "supabase_auth"
    DEV = "dev"


@dataclass(frozen=True)
class UserContext:
    """Authenticated user identity expected by application services."""

    user_id: uuid.UUID
    provider: AuthProviderKind
    email: str | None = None
