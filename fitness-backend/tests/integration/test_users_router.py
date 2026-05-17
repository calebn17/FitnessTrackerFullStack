"""Integration tests for /api/v1/users routes (Postgres + migrations)."""

import os
import time
from collections.abc import AsyncGenerator

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings, get_settings
from app.dependencies import get_db_session
from app.domains.ai import models as _ai_models  # noqa: F401
from app.domains.workouts import models as _workout_models  # noqa: F401
from app.main import create_app

_SECRET = "integration-test-jwt-secret-32bytes-min"
_AUDIENCE = "authenticated"


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://fitness:fitness@127.0.0.1:5433/fitness",
    )


def _encode_claims(**payload_overrides: object) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": "33333333-3333-3333-3333-333333333333",
        "email": "router-user@example.com",
        "aud": _AUDIENCE,
        "exp": now + 3600,
    }
    payload.update(payload_overrides)
    return jwt.encode(payload, _SECRET, algorithm="HS256")


@pytest.fixture
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[TestClient, None]:
    # Trigger fixture-backed DB setup/cleanup for this test case.
    assert db_session is not None

    def override_settings() -> Settings:
        return Settings(
            database_url=_database_url(),
            supabase_jwt_secret=_SECRET,
            supabase_jwt_audience=_AUDIENCE,
        )

    async def override_db_session() -> AsyncGenerator[AsyncSession, None]:
        # Create/close engine within app request loop to avoid cross-loop asyncpg issues.
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
async def test_users_me_unauthorized(client: TestClient) -> None:
    r = client.get("/api/v1/users/me")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "missing_authorization"


@pytest.mark.asyncio
async def test_users_me_invalid_token(client: TestClient) -> None:
    r = client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer totally.not.a.jwt"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "token_invalid"


@pytest.mark.asyncio
async def test_users_me_first_authenticated_request_creates_user(
    client: TestClient,
) -> None:
    token = _encode_claims(
        sub="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", email="new1@example.com"
    )
    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["supabase_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert body["email"] == "new1@example.com"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


@pytest.mark.asyncio
async def test_users_me_returns_existing_user(client: TestClient) -> None:
    sub = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    token1 = _encode_claims(sub=sub, email="stable@example.com")
    first = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token1}"}
    )
    assert first.status_code == 200
    fid = first.json()["id"]

    token2 = _encode_claims(
        sub=sub, email="stable@example.com", exp=int(time.time()) + 7200
    )
    second = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token2}"}
    )
    assert second.status_code == 200
    assert second.json()["id"] == fid


@pytest.mark.asyncio
async def test_users_me_missing_email_claim_returns_422(client: TestClient) -> None:
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            "aud": _AUDIENCE,
            "exp": now + 3600,
        },
        _SECRET,
        algorithm="HS256",
    )
    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invalid_user_claims"
