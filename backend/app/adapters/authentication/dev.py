"""Development authentication: one tenant per credential, never a shared one.

Explicitly dev-only, and deliberately *not* a stub that returns a single user. Returning
one fixed identity for every request means any credentials resolve to the same tenant, so
"sign in with a different account" silently hands over that tenant's templates. Here a
credential determines the identity instead:

* A real Supabase JWT is recognised and its ``sub`` claim is used, so a genuine signup that
  reaches a development-configured backend keeps its own tenant instead of being remapped
  onto the demo user.
* Any other credential maps to an explicit entry in ``DEV_AUTH_USERS`` when one matches
  (this is how the seeded demo user keeps its templates).
* Otherwise the credential is hashed into a stable per-credential id, so the same
  credential always means the same tenant and two credentials never collide.

It must never be enabled in production: the JWT signature is deliberately NOT verified,
because verifying it is :class:`SupabaseAuthProvider`'s job. Reading ``sub`` keeps a real
identity intact without pretending to authenticate it. Like every provider it returns the
same :class:`UserContext` shape, and it does not weaken RLS — a derived identity gets an
empty tenant, not another tenant's rows.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Mapping

from app.domain.models.user import AuthProviderKind, UserContext

__all__ = [
    "DEV_AUTH_NAMESPACE",
    "DEV_USER_EMAIL",
    "DEV_USER_ID",
    "DevAuthProvider",
    "derive_dev_user_id",
    "parse_dev_auth_users",
]

DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
DEV_USER_EMAIL = "demo@hive.test"

# Fixed namespace so a credential maps to the same id across restarts, processes and
# machines. Changing it would orphan every derived dev identity's templates.
DEV_AUTH_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

# Prefix the frontend puts on development credentials so they are recognisably not JWTs.
DEV_CREDENTIAL_PREFIX = "dev:"


def _normalize(credential: str) -> str:
    """Reduce a credential to its canonical lookup form."""

    value = credential.strip()
    if value.lower().startswith(DEV_CREDENTIAL_PREFIX):
        value = value[len(DEV_CREDENTIAL_PREFIX) :]
    return value.strip().lower()


def parse_dev_auth_users(raw: str) -> dict[str, uuid.UUID]:
    """Parse ``DEV_AUTH_USERS`` (``email=user-id`` pairs, comma separated).

    Malformed entries are skipped rather than raising: a typo in a development-only setting
    should degrade to "this credential gets its own tenant", not stop the API from booting.
    """

    mapping: dict[str, uuid.UUID] = {}
    for entry in raw.split(","):
        if "=" not in entry:
            continue
        email, _, raw_id = entry.partition("=")
        email = email.strip().lower()
        if not email:
            continue
        try:
            mapping[email] = uuid.UUID(raw_id.strip())
        except ValueError:
            continue
    return mapping


def _jwt_subject(token: str) -> uuid.UUID | None:
    """Return a JWT's ``sub`` claim when it is a UUID, else ``None``.

    The signature is not verified — see the module docstring. A malformed or unsigned blob
    simply is not treated as a JWT, and the caller falls back to deriving an identity from
    the token text.
    """

    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except ValueError:  # binascii.Error and JSONDecodeError both derive from ValueError
        return None
    if not isinstance(claims, dict):
        return None
    subject = claims.get("sub")
    if not isinstance(subject, str):
        return None
    try:
        return uuid.UUID(subject)
    except ValueError:
        return None


def derive_dev_user_id(
    credential: str, *, known_users: Mapping[str, uuid.UUID] | None = None
) -> uuid.UUID:
    """Map a development credential to a stable user id.

    A configured ``known_users`` entry wins so the seeded demo user keeps its templates;
    everything else is hashed into the namespace, which is stable per credential and
    distinct between credentials.
    """

    normalized = _normalize(credential)
    if not normalized:
        raise ValueError("A non-empty development credential is required.")
    if known_users:
        configured = known_users.get(normalized)
        if configured is not None:
            return configured
    return uuid.uuid5(DEV_AUTH_NAMESPACE, normalized)


class DevAuthProvider:
    """Resolves each request to the tenant its credential identifies.

    ``known_users`` maps credentials to explicit ids (see :func:`parse_dev_auth_users`).
    """

    def __init__(self, known_users: Mapping[str, uuid.UUID] | None = None) -> None:
        self._known_users = {_normalize(key): value for key, value in (known_users or {}).items()}

    async def get_current_user(self, token: str) -> UserContext:
        """Resolve ``token`` to a :class:`UserContext`, rejecting an empty credential."""

        if not token or not token.strip():
            raise ValueError("A non-empty development credential is required.")

        subject = _jwt_subject(token)
        if subject is not None:
            return UserContext(user_id=subject, provider=AuthProviderKind.DEV)

        normalized = _normalize(token)
        if not normalized:
            raise ValueError("A non-empty development credential is required.")
        return UserContext(
            user_id=derive_dev_user_id(normalized, known_users=self._known_users),
            provider=AuthProviderKind.DEV,
            email=normalized if "@" in normalized else None,
        )
