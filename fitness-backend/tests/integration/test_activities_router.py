"""Integration tests for Strava activities routes."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings, get_settings
from app.dependencies import get_db_session
from app.domains.activities import models as _activities_models  # noqa: F401
from app.domains.activities.models import PROVIDER_STRAVA, StravaActivity
from app.domains.activities.repository import OAuthTokenRepository
from app.domains.health import models as _health_models  # noqa: F401
from app.domains.users.repository import UserRepository
from app.main import create_app

_SECRET = "integration-test-jwt-secret-32bytes-min"
_AUDIENCE = "authenticated"
_SUB = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://fitness:fitness@127.0.0.1:5433/fitness",
    )


def _encode_claims(**overrides: object) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": _SUB,
        "email": "activities-router@example.com",
        "aud": _AUDIENCE,
        "exp": now + 3600,
    }
    payload.update(overrides)
    return jwt.encode(payload, _SECRET, algorithm="HS256")


@pytest.fixture
async def client(db_session: AsyncSession):
    assert db_session is not None

    def override_settings() -> Settings:
        return Settings(
            database_url=_database_url(),
            supabase_jwt_secret=_SECRET,
            supabase_jwt_audience=_AUDIENCE,
            strava_client_id="strava-id",
            strava_client_secret="strava-secret",
        )

    async def override_db_session():
        engine = create_async_engine(_database_url())
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session
        await engine.dispose()

    app = create_app()
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_encode_claims()}"}


@pytest.mark.asyncio
async def test_activities_recent_returns_stored_runs(
    client: TestClient,
    db_session: AsyncSession,
) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id=_SUB, email="activities-router@example.com")
    tokens = OAuthTokenRepository(db_session)
    await tokens.upsert(
        user_id=user.id,
        provider=PROVIDER_STRAVA,
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    token = await tokens.get_for_user_provider(user.id, PROVIDER_STRAVA)
    assert token is not None
    token.last_synced_at = datetime.now(UTC)
    activity = StravaActivity(
        user_id=user.id,
        strava_id=9001,
        sport_type="Run",
        start_date_local=datetime.now(UTC),
        distance=8046.72,
        moving_time=2400,
        elapsed_time=2520,
        average_speed=3.35,
        total_elevation_gain=45.0,
        pr_count=0,
    )
    db_session.add(activity)
    await db_session.commit()

    response = client.get("/api/v1/activities/recent", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert len(body["activities"]) == 1
    assert body["activities"][0]["distance_miles"] == 5.0
    assert body["synced_at"] is not None


@pytest.fixture
async def client_no_strava(db_session: AsyncSession):
    assert db_session is not None

    def override_settings() -> Settings:
        return Settings(
            database_url=_database_url(),
            supabase_jwt_secret=_SECRET,
            supabase_jwt_audience=_AUDIENCE,
            strava_client_id="",
            strava_client_secret="",
        )

    async def override_db_session():
        engine = create_async_engine(_database_url())
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session
        await engine.dispose()

    app = create_app()
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_strava_authorize_requires_credentials(client_no_strava: TestClient) -> None:
    response = client_no_strava.get(
        "/api/v1/auth/strava/authorize",
        headers=_auth_headers(),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "provider_not_configured"
