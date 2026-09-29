"""Unit tests for the authentication boundary.

The dev stub and the production Supabase provider both satisfy the
``AuthenticationProvider`` protocol and return the same :class:`UserContext` shape — the
application must not be able to tell them apart at the boundary.
"""

from __future__ import annotations

import asyncio
import uuid

from app.adapters.authentication.dev import DEV_USER_ID, DevAuthProvider
from app.domain.models.user import AuthProviderKind, UserContext
from app.protocols.authentication import AuthenticationProvider


def test_dev_provider_satisfies_protocol() -> None:
    assert isinstance(DevAuthProvider(), AuthenticationProvider)


def test_dev_provider_returns_deterministic_user_context() -> None:
    async def _get() -> UserContext:
        return await DevAuthProvider().get_current_user(token="whatever")

    context: UserContext = asyncio.run(_get())
    assert isinstance(context, UserContext)
    assert context.user_id == uuid.UUID("00000000-0000-0000-0000-000000000001")
    assert context.user_id == DEV_USER_ID
    assert context.provider is AuthProviderKind.DEV
    assert context.email is None


def test_dev_provider_ignores_the_token_value() -> None:
    async def _get() -> UserContext:
        return await DevAuthProvider().get_current_user(token="")

    assert asyncio.run(_get()).user_id == DEV_USER_ID
