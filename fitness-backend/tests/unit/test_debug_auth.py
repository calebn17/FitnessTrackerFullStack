"""Tests for debug auth bypass in get_supabase_jwt_claims."""

import time
from typing import Annotated, Any

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.core.security import get_supabase_jwt_claims

_SECRET = "debug-auth-test-secret-at-least-32-bytes-long"
_AUDIENCE = "authenticated"
_DEBUG_TOKEN = "fitnesstracker-debug-user"
_DEBUG_USER_ID = "debug-user"


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/claims")
    def read_claims(
        claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    ) -> dict[str, Any]:
        return claims

    return app


def _encode(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, _SECRET, algorithm="HS256")


def _valid_payload(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    base: dict[str, Any] = {
        "sub": "22222222-2222-2222-2222-222222222222",
        "aud": _AUDIENCE,
        "exp": now + 3600,
    }
    base.update(overrides)
    return base


@pytest.fixture
def debug_enabled_client() -> TestClient:
    get_settings.cache_clear()
    app = _make_app()

    def _settings() -> Settings:
        return Settings(
            debug_auth_enabled=True,
            supabase_jwt_secret=_SECRET,
            supabase_jwt_audience=_AUDIENCE,
        )

    app.dependency_overrides[get_settings] = _settings
    client = TestClient(app)
    yield client
    client.close()
    get_settings.cache_clear()


@pytest.fixture
def debug_disabled_client() -> TestClient:
    get_settings.cache_clear()
    app = _make_app()

    def _settings() -> Settings:
        return Settings(
            debug_auth_enabled=False,
            supabase_jwt_secret=_SECRET,
            supabase_jwt_audience=_AUDIENCE,
        )

    app.dependency_overrides[get_settings] = _settings
    client = TestClient(app)
    yield client
    client.close()
    get_settings.cache_clear()


def test_debug_token_returns_synthetic_claims(debug_enabled_client: TestClient) -> None:
    r = debug_enabled_client.get(
        "/claims",
        headers={"Authorization": f"Bearer {_DEBUG_TOKEN}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sub"] == _DEBUG_USER_ID
    assert body["aud"] == _AUDIENCE


def test_debug_token_rejected_when_disabled(debug_disabled_client: TestClient) -> None:
    r = debug_disabled_client.get(
        "/claims",
        headers={"Authorization": f"Bearer {_DEBUG_TOKEN}"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "token_invalid"


def test_real_jwt_still_works_when_debug_enabled(
    debug_enabled_client: TestClient,
) -> None:
    token = _encode(_valid_payload())
    r = debug_enabled_client.get(
        "/claims",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["sub"] == "22222222-2222-2222-2222-222222222222"


def test_non_debug_token_still_rejected_when_debug_enabled(
    debug_enabled_client: TestClient,
) -> None:
    r = debug_enabled_client.get(
        "/claims",
        headers={"Authorization": "Bearer some-random-invalid-token"},
    )
    assert r.status_code == 401
