"""Production authentication placeholder (Supabase Auth).

Satisfies the ``AuthenticationProvider`` protocol shape and documents the production path:
validate the Supabase access token (JWT) sent by the client, resolve ``auth.users.id``, and
return the SAME :class:`UserContext` shape the dev stub returns. That identity becomes
``templates.owner_id``. Full JWT validation wiring lands with the authentication/API step;
until then this provider fails closed.
"""

from __future__ import annotations

from app.domain.models.user import UserContext

__all__ = ["SupabaseAuthProvider"]


class SupabaseAuthProvider:
    """Authenticates users via Supabase Auth (not yet wired)."""

    async def get_current_user(self) -> UserContext:
        raise NotImplementedError(
            "SupabaseAuthProvider is not implemented yet; it will validate a Supabase "
            "access token and return a UserContext. Use DevAuthProvider in development."
        )