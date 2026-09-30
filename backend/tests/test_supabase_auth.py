"""Tests for real Supabase JWT validation (production auth).

Unit tests exercise :class:`SupabaseAuthProvider` against tokens minted with a test
secret (same HMAC scheme Supabase uses); API tests swap the provider into the app's
dependency graph (production-style wiring) and assert the §4 envelope on a live route:
``401 AUTHENTICATION_REQUIRED`` when the header is missing, ``401 INVALID_TOKEN`` for any
rejection (bad signature, expired, non-authenticated role), ``200`` for a genuine token.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from app.adapters.authentication.supabase import SupabaseAuthProvider
from app.adapters.repositories.in_memory import InMemoryTemplateRepository
from app.api.dependencies.auth import get_auth_provider, provision_identity, resolve_current_user
from app.api.dependencies.providers import get_template_repository
from app.domain.models.user import AuthProviderKind, UserContext
from app.main import create_app
from app.protocols.authentication import AuthenticationProvider

SECRET = "test-supabase-jwt-secret"
SUPABASE_URL = "https://example.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
EMAIL = "inspector@example.com"


def _mint(
    *,
    secret: str = SECRET,
    sub: str = str(USER_ID),
    role: str = "authenticated",
    aud: str = "authenticated",
    email: str = EMAIL,
    issuer: str = ISSUER,
    exp: datetime | None = None,
    omit: str | None = None,
) -> str:
    """Mint an HS256 JWT shaped like a Supabase access token."""
    now = datetime.now(UTC)
    payload: dict = {
        "iss": issuer,
        "sub": sub,
        "aud": aud,
        "exp": int((exp or (now + timedelta(hours=1))).timestamp()),
        "iat": int(now.timestamp()),
        "role": role,
        "email": email,
    }
    if omit:
        payload.pop(omit)
    return jwt.encode(payload, secret, algorithm="HS256")


# ---------------------------------------------------------------------------
# Provider unit tests
# ---------------------------------------------------------------------------


def test_provider_satisfies_protocol() -> None:
    assert isinstance(SupabaseAuthProvider(jwt_secret=SECRET), AuthenticationProvider)


def test_provider_without_a_secret_fails_closed_for_hs256() -> None:
    async def _run() -> None:
        provider = SupabaseAuthProvider(jwt_secret=None)
        await provider.get_current_user(token=_mint())

    with pytest.raises(jwt.InvalidTokenError, match="SUPABASE_JWT_SECRET required"):
        asyncio.run(_run())


def test_provider_accepts_valid_access_token() -> None:
    async def _run() -> UserContext:
        provider = SupabaseAuthProvider(jwt_secret=SECRET, supabase_url=SUPABASE_URL)
        return await provider.get_current_user(token=_mint())

    context = asyncio.run(_run())
    assert context.user_id == USER_ID
    assert context.provider is AuthProviderKind.SUPABASE_AUTH
    assert context.email == EMAIL


def test_provider_accepts_token_without_issuer_when_url_unset() -> None:
    async def _run() -> UserContext:
        provider = SupabaseAuthProvider(jwt_secret=SECRET)
        return await provider.get_current_user(token=_mint(issuer="other.example"))

    assert asyncio.run(_run()).user_id == USER_ID


@pytest.mark.parametrize(
    "reason",
    [
        "bad signature",
        "expired",
        "wrong role (anon key)",
        "wrong role (service_role key)",
        "wrong audience",
        "wrong issuer",
        "malformed token",
        "sub is not a uuid",
        "no exp claim",
        "no sub claim",
    ],
)
def test_provider_rejects_invalid_credentials(reason: str) -> None:
    if reason == "bad signature":
        token = _mint(secret="another-secret")
    elif reason == "expired":
        token = _mint(exp=datetime.now(UTC) - timedelta(seconds=1))
    elif reason == "wrong role (anon key)":
        token = _mint(role="anon")
    elif reason == "wrong role (service_role key)":
        token = _mint(role="service_role")
    elif reason == "wrong audience":
        token = _mint(aud="service_role")
    elif reason == "wrong issuer":
        token = _mint(issuer="https://evil.example/auth/v1")
    elif reason == "malformed token":
        token = "not.a.jwt"
    elif reason == "sub is not a uuid":
        token = _mint(sub="not-a-uuid")
    elif reason == "no exp claim":
        token = _mint(omit="exp")
    else:  # no sub claim
        token = _mint(omit="sub")

    async def _run() -> None:
        provider = SupabaseAuthProvider(jwt_secret=SECRET, supabase_url=SUPABASE_URL)
        await provider.get_current_user(token=token)

    with pytest.raises(jwt.InvalidTokenError):
        asyncio.run(_run())


# ---------------------------------------------------------------------------
# API wiring (production provider injected, like APP_ENV=production)
# ---------------------------------------------------------------------------


async def _skip_provisioning(
    user: Annotated[UserContext, Depends(resolve_current_user)],
) -> UserContext:
    """The repository is stubbed here, so identity provisioning has nothing to write to."""

    return user


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    repository = InMemoryTemplateRepository()
    app.dependency_overrides[get_template_repository] = lambda: repository
    app.dependency_overrides[provision_identity] = _skip_provisioning
    app.dependency_overrides[get_auth_provider] = lambda: SupabaseAuthProvider(
        jwt_secret=SECRET, supabase_url=SUPABASE_URL
    )
    with TestClient(app) as test_client:
        yield test_client


def test_missing_header_is_authentication_required(client: TestClient) -> None:
    response = client.get("/api/templates")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert response.headers["www-authenticate"] == "Bearer"


def test_valid_token_succeeds(client: TestClient) -> None:
    response = client.get("/api/templates", headers={"Authorization": f"Bearer {_mint()}"})
    assert response.status_code == 200
    assert response.json() == []


def test_invalid_token_is_invalid_token(client: TestClient) -> None:
    bad_tokens = (
        _mint(secret="wrong"),
        _mint(role="anon"),
        _mint(exp=datetime.now(UTC) - timedelta(minutes=1)),
    )
    for token in bad_tokens:
        response = client.get("/api/templates", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_TOKEN"
        assert response.headers["www-authenticate"] == "Bearer"


def test_health_route_stays_open(client: TestClient) -> None:
    # health sits outside the /api bearer dependency
    response = client.get("/health")
    assert response.status_code == 200


def test_provider_accepts_es256_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    now = datetime.now(UTC)
    payload = {
        "iss": ISSUER,
        "sub": str(USER_ID),
        "aud": "authenticated",
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "iat": int(now.timestamp()),
        "role": "authenticated",
        "email": EMAIL,
    }
    es256_token = jwt.encode(payload, private_key, algorithm="ES256")

    class DummySigningKey:
        def __init__(self, key: object) -> None:
            self.key = key

    class DummyJWKSClient:
        def get_signing_key_from_jwt(self, token: str) -> DummySigningKey:
            return DummySigningKey(public_key)

    provider = SupabaseAuthProvider(jwt_secret=SECRET, supabase_url=SUPABASE_URL)
    monkeypatch.setattr(provider, "_jwks_client", DummyJWKSClient())

    async def _run() -> UserContext:
        return await provider.get_current_user(token=es256_token)

    context = asyncio.run(_run())
    assert context.user_id == USER_ID
    assert context.email == EMAIL
