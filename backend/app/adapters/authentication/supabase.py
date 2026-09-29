"""Production authentication (Supabase Auth, real JWT validation).

Validates the Supabase access token a client sends in ``Authorization: Bearer <token>``
and returns the SAME :class:`UserContext` shape the dev stub returns; that identity
becomes ``templates.owner_id``.

Supabase signs its JWTs (access tokens **and** the ``anon``/``service_role`` API keys)
with the project's ``SUPABASE_JWT_SECRET`` using HS256. Signature/``exp`` verification
alone is therefore not enough to accept a credential as a logged-in user — an attacker
holding the public ``anon`` key could mint a "valid" token. Access tokens are further
bound by claims:

* ``aud`` must be ``authenticated`` (PyJWT ``audience`` verification);
* ``role`` must be ``authenticated`` — this rejects ``anon`` and ``service_role`` keys
  outright, and it is the check that keeps the API from authenticating as a robot user;
* ``sub`` (the ``auth.users`` id) must be a UUID — it becomes ``UserContext.user_id``.

When ``SUPABASE_URL`` is configured the token's ``iss`` (``<url>/auth/v1``) is verified
too. The provider fails closed: without a configured JWT secret it refuses to construct.
Invalid/expired/malformed credentials raise; the API layer maps every rejection to the
single ``401 INVALID_TOKEN`` envelope (§4), so an attacker learns nothing about *why* the
token failed.
"""

from __future__ import annotations

import uuid

import jwt

from app.domain.models.user import AuthProviderKind, UserContext

__all__ = ["SupabaseAuthProvider"]

_SUPABASE_ISSUER_PATH = "/auth/v1"


class SupabaseAuthProvider:
    """Authenticate users by verifying their Supabase Auth access token."""

    def __init__(self, *, jwt_secret: str, supabase_url: str | None = None) -> None:
        if not jwt_secret:
            raise ValueError("SUPABASE_JWT_SECRET is required to construct SupabaseAuthProvider")
        self._jwt_secret = jwt_secret
        if supabase_url:
            self._issuer = f"{supabase_url.rstrip('/')}{_SUPABASE_ISSUER_PATH}"
            self._jwks_client = jwt.PyJWKClient(f"{self._issuer}/.well-known/jwks.json")
        else:
            self._issuer = None
            self._jwks_client = None

    async def get_current_user(self, token: str) -> UserContext:
        claims = self._decode(token)
        if claims["role"] != "authenticated":
            raise jwt.InvalidTokenError("token role is not 'authenticated'")
        try:
            user_id = uuid.UUID(claims["sub"])
        except (KeyError, ValueError) as exc:
            raise jwt.InvalidTokenError("token sub is not a valid user id") from exc
        return UserContext(
            user_id=user_id,
            provider=AuthProviderKind.SUPABASE_AUTH,
            email=claims.get("email"),
        )

    def _decode(self, token: str) -> dict:
        """Verify signature, expiration, audience, and (when configured) issuer."""
        try:
            unverified_header = jwt.get_unverified_header(token)
            alg = unverified_header.get("alg", "HS256")

            if alg == "RS256" and self._jwks_client:
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                key = signing_key.key
            else:
                key = self._jwt_secret
                alg = "HS256"

            payload = jwt.decode(
                token,
                key,
                algorithms=[alg],
                audience="authenticated",
                issuer=self._issuer,
                options={"require": ["exp", "sub", "aud", "role"]},
            )
        except jwt.InvalidTokenError:
            raise
        except Exception as exc:  # pragma: no cover - PyJWT raises InvalidTokenError subtypes
            raise jwt.InvalidTokenError("token could not be verified") from exc
        return payload
