"""Unit tests for shared OAuth helpers."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.oauth import (
    OAuthRefreshConfig,
    OAuthStateError,
    OAuthStateStore,
    ProviderAuthExpiredError,
    ensure_valid_token,
    exchange_strava_code,
    refresh_strava_token,
)
from app.domains.activities.models import OAuthToken


@pytest.mark.asyncio
async def test_oauth_state_store_create_and_consume() -> None:
    store = OAuthStateStore()
    user_id = uuid.uuid4()
    state = store.create(user_id)
    assert store.consume(state) == user_id


def test_oauth_state_store_expired() -> None:
    store = OAuthStateStore()
    user_id = uuid.uuid4()
    state = store.create(user_id)
    store._states[state] = (user_id, time.monotonic() - 1)
    with pytest.raises(OAuthStateError):
        store.consume(state)


@pytest.mark.asyncio
async def test_exchange_strava_code_parses_response() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": 1893456000,
                "athlete": {"id": 42},
                "scope": "activity:read_all",
            },
        ),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        payload = await exchange_strava_code(
            code="abc",
            client_id="id",
            client_secret="secret",
            redirect_uri="http://localhost/callback",
            http_client=client,
        )
    assert payload.access_token == "access"
    assert payload.athlete_id == "42"
    assert payload.scopes == "activity:read_all"


@pytest.mark.asyncio
async def test_refresh_strava_token_auth_expired() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(401, json={"message": "invalid"}),
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ProviderAuthExpiredError):
            await refresh_strava_token(
                refresh_token="old",
                client_id="id",
                client_secret="secret",
                http_client=client,
            )


@pytest.mark.asyncio
async def test_ensure_valid_token_refreshes_when_expiring(db_session) -> None:
    from app.domains.users.repository import UserRepository

    users = UserRepository(db_session)
    user = await users.create(supabase_id="oauth-refresh-sub", email="oauth-refresh@example.com")
    token = OAuthToken(
        user_id=user.id,
        provider="strava",
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    )
    db_session.add(token)
    await db_session.flush()

    refreshed_at = datetime.now(UTC) + timedelta(hours=1)
    config = OAuthRefreshConfig(
        token_url="https://example.com/token",
        client_id="id",
        client_secret="secret",
    )

    from app.core.oauth import OAuthTokenPayload

    refreshed = OAuthTokenPayload(
        access_token="new-access",
        refresh_token="new-refresh",
        expires_at=refreshed_at,
    )
    with patch(
        "app.core.oauth.refresh_strava_token",
        new_callable=AsyncMock,
        return_value=refreshed,
    ) as mock_refresh:
        result = await ensure_valid_token(
            token,
            config,
            db_session,
            refresh_fn=mock_refresh,
        )

    assert result.access_token == "new-access"
    assert result.refresh_token == "new-refresh"
    mock_refresh.assert_awaited_once()
