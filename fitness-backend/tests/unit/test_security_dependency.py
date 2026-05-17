"""Tests for Bearer JWT dependency and stable 401 error codes."""

import time
from typing import Annotated, Any

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.core.security import get_supabase_jwt_claims

_SECRET = "dependency-test-jwt-secret-at-least-32-bytes"
_AUDIENCE = "authenticated"


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
def client() -> TestClient:
    get_settings.cache_clear()
    app = _make_app()

    def _settings() -> Settings:
        return Settings(
            supabase_jwt_secret=_SECRET,
            supabase_jwt_audience=_AUDIENCE,
        )

    app.dependency_overrides[get_settings] = _settings
    test_client = TestClient(app)
    yield test_client
    test_client.close()
    get_settings.cache_clear()


def test_missing_authorization_header(client: TestClient) -> None:
    r = client.get("/claims")
    assert r.status_code == 401
    assert r.json() == {
        "detail": {
            "code": "missing_authorization",
            "message": "Authorization header is missing.",
        }
    }


def test_invalid_authorization_scheme(client: TestClient) -> None:
    r = client.get("/claims", headers={"Authorization": "Basic abc"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invalid_authorization_format"


def test_empty_bearer_token(client: TestClient) -> None:
    r = client.get("/claims", headers={"Authorization": "Bearer "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invalid_authorization_format"


def test_valid_bearer_token(client: TestClient) -> None:
    token = _encode(_valid_payload())
    r = client.get("/claims", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["sub"] == "22222222-2222-2222-2222-222222222222"


def test_expired_token(client: TestClient) -> None:
    token = _encode(_valid_payload(exp=int(time.time()) - 10))
    r = client.get("/claims", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "token_expired"


def test_invalid_signature(client: TestClient) -> None:
    other_secret = "other-secret-not-the-same-as-encoder__________"
    token = jwt.encode(_valid_payload(), other_secret, algorithm="HS256")
    r = client.get("/claims", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "token_invalid_signature"


def test_invalid_audience(client: TestClient) -> None:
    token = _encode(_valid_payload(aud="wrong-aud"))
    r = client.get("/claims", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "token_invalid_audience"


def test_malformed_token(client: TestClient) -> None:
    r = client.get("/claims", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "token_invalid"


def test_missing_required_claim_returns_code(client: TestClient) -> None:
    payload = _valid_payload()
    del payload["aud"]
    token = jwt.encode(payload, _SECRET, algorithm="HS256")
    r = client.get("/claims", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    body = r.json()["detail"]
    assert body["code"] == "token_missing_claim"
    assert body["claim"] == "aud"


def test_auth_not_configured_when_secret_empty() -> None:
    get_settings.cache_clear()
    app = _make_app()

    def _settings() -> Settings:
        return Settings(supabase_jwt_secret="", supabase_jwt_audience=_AUDIENCE)

    app.dependency_overrides[get_settings] = _settings
    client = TestClient(app)
    token = _encode(_valid_payload())
    r = client.get("/claims", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth_not_configured"
    client.close()
    get_settings.cache_clear()
