"""Unit tests for the authentication boundary.

The dev provider and the production Supabase provider both satisfy the
``AuthenticationProvider`` protocol and return the same :class:`UserContext` shape — the
application must not be able to tell them apart at the boundary.

The dev provider's job is to make the credential decide the tenant: one fixed identity for
every request would hand any sign-in the same templates, which is the bug these tests guard.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid

import pytest

from app.adapters.authentication.dev import (
    DEV_AUTH_NAMESPACE,
    DEV_USER_EMAIL,
    DEV_USER_ID,
    DevAuthProvider,
    derive_dev_user_id,
    parse_dev_auth_users,
)
from app.domain.models.user import AuthProviderKind, UserContext
from app.protocols.authentication import AuthenticationProvider

DEMO = DEV_USER_EMAIL
KNOWN = {DEMO: DEV_USER_ID}


def _resolve(token: str, *, known: dict[str, uuid.UUID] | None = None) -> UserContext:
    async def _get() -> UserContext:
        return await DevAuthProvider(known if known is not None else KNOWN).get_current_user(
            token=token
        )

    return asyncio.run(_get())


def _jwt(sub: str) -> str:
    """Build an unsigned JWT with the given ``sub`` (the dev provider reads claims only)."""

    def segment(payload: dict[str, object]) -> str:
        raw = json.dumps(payload).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{segment({'alg': 'HS256'})}.{segment({'sub': sub})}.signature"


def test_dev_provider_satisfies_protocol() -> None:
    assert isinstance(DevAuthProvider(), AuthenticationProvider)


def test_configured_credential_resolves_to_the_seeded_demo_user() -> None:
    context = _resolve(f"dev:{DEMO}")
    assert context.user_id == DEV_USER_ID
    assert context.provider is AuthProviderKind.DEV


def test_credential_prefix_is_optional_and_case_insensitive() -> None:
    assert _resolve(DEMO).user_id == DEV_USER_ID
    assert _resolve(f"  DEV:{DEMO.upper()}  ").user_id == DEV_USER_ID


def test_unknown_credential_gets_its_own_stable_tenant() -> None:
    first = _resolve("dev:someone@example.test")
    again = _resolve("dev:someone@example.test")
    assert first.user_id == again.user_id
    assert first.user_id != DEV_USER_ID


def test_two_unknown_credentials_are_different_tenants() -> None:
    """The core of the reported bug: two sign-ins must not share a workspace."""

    alice = _resolve("dev:alice@example.test")
    bob = _resolve("dev:bob@example.test")
    assert alice.user_id != bob.user_id


def test_derived_identity_is_reproducible_from_the_credential_alone() -> None:
    """A restart must not orphan a dev user's templates, so the mapping is deterministic."""

    assert derive_dev_user_id("dev:someone@example.test") == uuid.uuid5(
        DEV_AUTH_NAMESPACE, "someone@example.test"
    )


def test_derived_identity_is_unlikely_to_collide_with_a_seeded_id() -> None:
    assert derive_dev_user_id("dev:anything") not in {DEV_USER_ID}


def test_real_jwt_subject_is_honoured() -> None:
    """A genuine Supabase user must keep its own tenant, not be remapped to the demo one."""

    sub = "3f2a1c9e-7b6d-4a1f-9c2e-5d8b0a4e6f13"
    context = _resolve(_jwt(sub))
    assert context.user_id == uuid.UUID(sub)
    assert context.user_id != DEV_USER_ID


def test_malformed_token_falls_back_to_deriving_an_identity() -> None:
    context = _resolve("dev:not.a.jwt")
    assert context.user_id == uuid.uuid5(DEV_AUTH_NAMESPACE, "not.a.jwt")


def test_unparseable_jwt_payload_falls_back_to_deriving_an_identity() -> None:
    token = "dev:aaa.!!!not-base64!!!.ccc"
    context = _resolve(token)
    assert context.user_id == derive_dev_user_id(token)
    assert context.user_id != DEV_USER_ID


def test_jwt_without_uuid_subject_falls_back_to_deriving_an_identity() -> None:
    token = _jwt("not-a-uuid")
    context = _resolve(token)
    assert context.user_id == derive_dev_user_id(token)
    assert context.user_id != DEV_USER_ID


def test_email_is_reported_for_email_credentials_only() -> None:
    assert _resolve("dev:alice@example.test").email == "alice@example.test"
    assert _resolve("dev:opaque-token").email is None
    assert _resolve(_jwt("3f2a1c9e-7b6d-4a1f-9c2e-5d8b0a4e6f13")).email is None


@pytest.mark.parametrize("token", ["", "   "])
def test_empty_credential_is_rejected(token: str) -> None:
    with pytest.raises(ValueError):
        _resolve(token)


def test_parse_dev_auth_users_reads_pairs_and_skips_malformed_entries() -> None:
    parsed = parse_dev_auth_users(
        f"{DEMO}={DEV_USER_ID}, broken, other@example.test=not-a-uuid, =orphan, "
        "third@example.test=00000000-0000-0000-0000-000000000002"
    )
    assert parsed == {
        DEMO: DEV_USER_ID,
        "third@example.test": uuid.UUID("00000000-0000-0000-0000-000000000002"),
    }


def test_default_configuration_maps_the_demo_email_to_the_seeded_user() -> None:
    """Guards the .env.example default against drifting away from dev_auth.sql."""

    from app.infrastructure.config.settings import Settings

    assert parse_dev_auth_users(Settings().dev_auth_users)[DEMO] == DEV_USER_ID
