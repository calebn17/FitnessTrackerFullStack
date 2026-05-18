"""Integration tests for observability middleware, metrics, and request IDs."""

from __future__ import annotations

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
        "email": "obs@example.com",
        "aud": _AUDIENCE,
        "exp": now + 3600,
    }
    payload.update(payload_overrides)
    return jwt.encode(payload, _SECRET, algorithm="HS256")


@pytest.fixture
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[TestClient, None]:
    assert db_session is not None

    def override_settings() -> Settings:
        return Settings(
            database_url=_database_url(),
            supabase_jwt_secret=_SECRET,
            supabase_jwt_audience=_AUDIENCE,
        )

    async def override_db_session() -> AsyncGenerator[AsyncSession, None]:
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
async def test_x_request_id_propagated_or_generated(client: TestClient) -> None:
    r1 = client.get("/health")
    assert r1.status_code == 200
    assert "x-request-id" in r1.headers
    rid = r1.headers["x-request-id"]
    assert len(rid) > 0

    r2 = client.get("/health", headers={"X-Request-ID": "  custom-id  "})
    assert r2.status_code == 200
    assert r2.headers["x-request-id"] == "custom-id"


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    ct = r.headers.get("content-type", "").lower()
    assert "text/plain" in ct
    assert "version=" in ct
    body = r.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body


@pytest.mark.asyncio
async def test_authenticated_request_logs_include_user_id_in_json(
    client: TestClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    token = _encode_claims(sub="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", email="u@example.com")
    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if "http.request" in ln and "/api/v1/users/me" in ln]
    assert lines, "expected at least one http.request log line for /users/me"
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in lines[-1]
