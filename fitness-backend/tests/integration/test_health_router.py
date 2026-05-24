"""Integration tests for Whoop health routes."""

from __future__ import annotations

import os
import time
from datetime import UTC, date, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings, get_settings
from app.dependencies import get_db_session
from app.domains.activities import models as _activities_models  # noqa: F401
from app.domains.activities.models import PROVIDER_WHOOP
from app.domains.activities.repository import OAuthTokenRepository
from app.domains.health import models as _health_models  # noqa: F401
from app.domains.health.models import DailyHealthRecord
from app.domains.users.repository import UserRepository
from app.main import create_app

_SECRET = "integration-test-jwt-secret-32bytes-min"
_AUDIENCE = "authenticated"
_SUB = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://fitness:fitness@127.0.0.1:5433/fitness",
    )


def _encode_claims(**overrides: object) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": _SUB,
        "email": "health-router@example.com",
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
            whoop_client_id="whoop-id",
            whoop_client_secret="whoop-secret",
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
async def test_health_today_returns_record(client: TestClient, db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id=_SUB, email="health-router@example.com")
    tokens = OAuthTokenRepository(db_session)
    await tokens.upsert(
        user_id=user.id,
        provider=PROVIDER_WHOOP,
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    token = await tokens.get_for_user_provider(user.id, PROVIDER_WHOOP)
    assert token is not None
    token.last_synced_at = datetime.now(UTC)
    db_session.add(
        DailyHealthRecord(
            user_id=user.id,
            date=date.today(),
            provider="whoop",
            sleep_score=85,
            recovery_score=78,
            strain_score=14.2,
        ),
    )
    await db_session.commit()

    response = client.get("/api/v1/health/today", headers=_auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["sleep"]["score"] == 85
    assert body["recovery"]["score"] == 78


@pytest.mark.asyncio
async def test_health_today_missing_returns_404(
    client: TestClient,
    db_session: AsyncSession,
) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="cccc-sub", email="health-missing@example.com")
    tokens = OAuthTokenRepository(db_session)
    await tokens.upsert(
        user_id=user.id,
        provider=PROVIDER_WHOOP,
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    token = await tokens.get_for_user_provider(user.id, PROVIDER_WHOOP)
    assert token is not None
    token.last_synced_at = datetime.now(UTC)
    await db_session.commit()

    token_str = jwt.encode(
        {
            "sub": "cccc-sub",
            "email": "health-missing@example.com",
            "aud": _AUDIENCE,
            "exp": int(time.time()) + 3600,
        },
        _SECRET,
        algorithm="HS256",
    )
    response = client.get(
        "/api/v1/health/today",
        headers={"Authorization": f"Bearer {token_str}"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "no_health_data"
