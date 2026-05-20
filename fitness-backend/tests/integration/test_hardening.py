"""Integration tests for Phase 8 hardening (rate limits, CORS, error sanitization)."""

from __future__ import annotations

import os
import time
import uuid
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
        "sub": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
        "email": "hardening@example.com",
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
            debug=False,
            environment="test",
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
async def test_security_headers_on_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    assert "Cache-Control" not in r.headers or "no-store" not in r.headers.get("Cache-Control", "")


@pytest.mark.asyncio
async def test_security_headers_api_includes_cache_control_no_store(client: TestClient) -> None:
    token = _encode_claims()
    r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Cache-Control") == "no-store"


@pytest.mark.asyncio
async def test_write_rate_limit_returns_429(client: TestClient) -> None:
    token = _encode_claims(
        sub="ffffffff-ffff-ffff-ffff-ffffffffffff",
        email="ratelimit@example.com",
    )
    headers = {"Authorization": f"Bearer {token}"}
    for _ in range(20):
        body = {
            "client_id": str(uuid.uuid4()),
            "date": "2026-06-01",
            "workout_type": "strength",
            "sets": [],
        }
        r = client.post("/api/v1/workouts", json=body, headers=headers)
        assert r.status_code == 201, r.text
    overflow = client.post(
        "/api/v1/workouts",
        json={
            "client_id": str(uuid.uuid4()),
            "date": "2026-06-02",
            "workout_type": "strength",
            "sets": [],
        },
        headers=headers,
    )
    assert overflow.status_code == 429
    err = overflow.json().get("error", overflow.text)
    assert "rate limit" in str(err).lower()


@pytest.mark.asyncio
async def test_write_rate_limit_uses_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    assert db_session is not None
    monkeypatch.setenv("RATE_LIMIT_WRITE", "1/minute")
    get_settings.cache_clear()

    def override_settings() -> Settings:
        return Settings(
            database_url=_database_url(),
            supabase_jwt_secret=_SECRET,
            supabase_jwt_audience=_AUDIENCE,
            debug=False,
            environment="test",
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
    token = _encode_claims(
        sub="abababab-abab-abab-abab-abababababab",
        email="configured-rate-limit@example.com",
    )
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with TestClient(app) as c:
            r1 = c.post("/api/v1/sync", json={"changes": []}, headers=headers)
            r2 = c.post("/api/v1/sync", json={"changes": []}, headers=headers)
    finally:
        app.dependency_overrides.clear()
        monkeypatch.delenv("RATE_LIMIT_WRITE", raising=False)
        get_settings.cache_clear()

    assert r1.status_code == 200, r1.text
    assert r2.status_code == 429


@pytest.mark.asyncio
async def test_cors_preflight_allows_configured_development_origin(client: TestClient) -> None:
    r = client.options(
        "/api/v1/users/me",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_production_with_explicit_origins_rejects_other_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://allowed.example")
    get_settings.cache_clear()
    try:
        app = create_app()
        with TestClient(app) as c:
            r = c.options(
                "/health",
                headers={
                    "Origin": "https://evil.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert r.headers.get("access-control-allow-origin") != "https://evil.example"
    finally:
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        get_settings.cache_clear()


def test_unhandled_exception_does_not_leak_message_when_debug_false() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(debug=False)

    @app.get("/__boom")
    async def boom() -> None:
        raise RuntimeError("secret-internals-do-not-leak")

    try:
        # ServerErrorMiddleware always re-raises after sending the 500 body so ASGI
        # servers/tests can observe the error; disable that for this assertion.
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/__boom")
        assert r.status_code == 500
        assert "secret-internals" not in r.text
        assert r.json()["detail"]["code"] == "internal_server_error"
        assert r.headers.get("X-Request-ID")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"
        assert r.headers.get("X-Frame-Options") == "DENY"
        assert r.headers.get("Referrer-Policy") == "no-referrer"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_http_exception_detail_unchanged(client: TestClient) -> None:
    r = client.get("/api/v1/users/me")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "missing_authorization"
