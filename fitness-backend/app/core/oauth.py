"""Shared OAuth helpers: state storage, token exchange, and refresh."""

from __future__ import annotations

import secrets
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.activities.models import OAuthToken

REFRESH_BUFFER = timedelta(minutes=5)
STATE_TTL_SECONDS = 300

_STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
_WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"


class ProviderAuthExpiredError(Exception):
    """Refresh token revoked or provider rejected re-auth."""


class ProviderCredentialsNotConfiguredError(Exception):
    """OAuth client id/secret missing for a provider."""


class OAuthStateError(Exception):
    """Invalid or expired OAuth CSRF state."""


@dataclass(frozen=True)
class OAuthRefreshConfig:
    """Provider token endpoint credentials."""

    token_url: str
    client_id: str
    client_secret: str


@dataclass(frozen=True)
class OAuthTokenPayload:
    """Normalized token response from a provider."""

    access_token: str
    refresh_token: str
    expires_at: datetime
    athlete_id: str | None = None
    scopes: str | None = None


class OAuthStateStore:
    """In-memory OAuth CSRF state with a five-minute TTL."""

    def __init__(self) -> None:
        self._states: dict[str, tuple[uuid.UUID, float]] = {}

    def _purge_expired(self, now: float) -> None:
        expired = [key for key, (_, expires) in self._states.items() if expires <= now]
        for key in expired:
            del self._states[key]

    def create(self, user_id: uuid.UUID) -> str:
        now = time.monotonic()
        self._purge_expired(now)
        state = secrets.token_urlsafe(32)
        self._states[state] = (user_id, now + STATE_TTL_SECONDS)
        return state

    def consume(self, state: str) -> uuid.UUID:
        now = time.monotonic()
        self._purge_expired(now)
        entry = self._states.pop(state, None)
        if entry is None:
            raise OAuthStateError("Invalid or expired OAuth state.")
        user_id, expires = entry
        if expires <= now:
            raise OAuthStateError("Invalid or expired OAuth state.")
        return user_id


oauth_state_store = OAuthStateStore()


def _parse_expires_at(payload: dict[str, Any]) -> datetime:
    if "expires_at" in payload and payload["expires_at"] is not None:
        raw = payload["expires_at"]
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(float(raw), tz=UTC)
        if isinstance(raw, str):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    expires_in = payload.get("expires_in")
    if expires_in is not None:
        return datetime.now(UTC) + timedelta(seconds=int(expires_in))
    raise ValueError("Token response missing expiry information.")


def _normalize_scopes(payload: dict[str, Any]) -> str | None:
    scope = payload.get("scope")
    if scope is None:
        return None
    if isinstance(scope, list):
        return ",".join(str(s) for s in scope)
    return str(scope)


async def exchange_strava_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    http_client: httpx.AsyncClient | None = None,
) -> OAuthTokenPayload:
    """Exchange a Strava authorization code for tokens."""
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    }
    async with _http_client(http_client) as client:
        response = await client.post(_STRAVA_TOKEN_URL, data=data)
        response.raise_for_status()
        payload = response.json()
    athlete = payload.get("athlete") or {}
    athlete_id = str(athlete.get("id")) if athlete.get("id") is not None else None
    return OAuthTokenPayload(
        access_token=str(payload["access_token"]),
        refresh_token=str(payload["refresh_token"]),
        expires_at=_parse_expires_at(payload),
        athlete_id=athlete_id,
        scopes=_normalize_scopes(payload),
    )


async def exchange_whoop_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    http_client: httpx.AsyncClient | None = None,
) -> OAuthTokenPayload:
    """Exchange a Whoop authorization code for tokens."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    async with _http_client(http_client) as client:
        response = await client.post(_WHOOP_TOKEN_URL, data=data)
        response.raise_for_status()
        payload = response.json()
    return OAuthTokenPayload(
        access_token=str(payload["access_token"]),
        refresh_token=str(payload["refresh_token"]),
        expires_at=_parse_expires_at(payload),
        athlete_id=str(payload["user_id"]) if payload.get("user_id") is not None else None,
        scopes=_normalize_scopes(payload),
    )


async def refresh_strava_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    http_client: httpx.AsyncClient | None = None,
) -> OAuthTokenPayload:
    """Refresh Strava tokens (refresh token rotates)."""
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    async with _http_client(http_client) as client:
        response = await client.post(_STRAVA_TOKEN_URL, data=data)
        if response.status_code in (400, 401):
            raise ProviderAuthExpiredError("Strava refresh token is invalid.")
        response.raise_for_status()
        payload = response.json()
    athlete = payload.get("athlete") or {}
    athlete_id = str(athlete.get("id")) if athlete.get("id") is not None else None
    return OAuthTokenPayload(
        access_token=str(payload["access_token"]),
        refresh_token=str(payload["refresh_token"]),
        expires_at=_parse_expires_at(payload),
        athlete_id=athlete_id,
        scopes=_normalize_scopes(payload),
    )


async def refresh_whoop_token(
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    http_client: httpx.AsyncClient | None = None,
) -> OAuthTokenPayload:
    """Refresh Whoop tokens (refresh token rotates)."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    async with _http_client(http_client) as client:
        response = await client.post(_WHOOP_TOKEN_URL, data=data)
        if response.status_code in (400, 401):
            raise ProviderAuthExpiredError("Whoop refresh token is invalid.")
        response.raise_for_status()
        payload = response.json()
    return OAuthTokenPayload(
        access_token=str(payload["access_token"]),
        refresh_token=str(payload["refresh_token"]),
        expires_at=_parse_expires_at(payload),
        athlete_id=str(payload.get("user_id")) if payload.get("user_id") is not None else None,
        scopes=_normalize_scopes(payload),
    )


async def ensure_valid_token(
    token: OAuthToken,
    config: OAuthRefreshConfig,
    session: AsyncSession,
    *,
    refresh_fn: Any,
    http_client: httpx.AsyncClient | None = None,
) -> OAuthToken:
    """Refresh the token if it expires within five minutes."""
    if token.expires_at > datetime.now(UTC) + REFRESH_BUFFER:
        return token
    try:
        refreshed = await refresh_fn(
            refresh_token=token.refresh_token,
            client_id=config.client_id,
            client_secret=config.client_secret,
            http_client=http_client,
        )
    except ProviderAuthExpiredError:
        raise
    token.access_token = refreshed.access_token
    token.refresh_token = refreshed.refresh_token
    token.expires_at = refreshed.expires_at
    if refreshed.athlete_id is not None:
        token.athlete_id = refreshed.athlete_id
    if refreshed.scopes is not None:
        token.scopes = refreshed.scopes
    token.updated_at = datetime.now(UTC)
    await session.flush()
    return token


@asynccontextmanager
async def _http_client(
    http_client: httpx.AsyncClient | None,
) -> AsyncIterator[httpx.AsyncClient]:
    if http_client is not None:
        yield http_client
    else:
        async with httpx.AsyncClient(timeout=30.0) as client:
            yield client
