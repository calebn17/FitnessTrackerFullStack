"""Unit tests for Supabase-style JWT validation (Phase 3)."""

import time
from typing import Any

import jwt
import pytest
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidSignatureError,
    InvalidTokenError,
    MissingRequiredClaimError,
)

from app.config import Settings
from app.core.security import decode_supabase_access_token

_TEST_SECRET = "unit-test-jwt-secret-at-least-32-bytes-long"
_TEST_AUDIENCE = "authenticated"


def _encode_token(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, _TEST_SECRET, algorithm="HS256")


def _valid_payload(**overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    base: dict[str, Any] = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "aud": _TEST_AUDIENCE,
        "exp": now + 3600,
        "role": "authenticated",
    }
    base.update(overrides)
    return base


def test_settings_supabase_auth_defaults() -> None:
    settings = Settings()
    assert settings.supabase_jwt_audience == "authenticated"
    assert settings.supabase_url == ""
    assert settings.supabase_jwt_secret == ""


def test_decode_valid_token() -> None:
    token = _encode_token(_valid_payload())
    claims = decode_supabase_access_token(
        token,
        jwt_secret=_TEST_SECRET,
        audience=_TEST_AUDIENCE,
    )
    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"
    assert claims["aud"] == _TEST_AUDIENCE


def test_decode_expired_token_raises() -> None:
    token = _encode_token(_valid_payload(exp=int(time.time()) - 60))
    with pytest.raises(ExpiredSignatureError):
        decode_supabase_access_token(
            token,
            jwt_secret=_TEST_SECRET,
            audience=_TEST_AUDIENCE,
        )


def test_decode_invalid_signature_raises() -> None:
    token = _encode_token(_valid_payload())
    with pytest.raises(InvalidSignatureError):
        decode_supabase_access_token(
            token,
            jwt_secret="wrong-secret-not-the-same-as-encoder________",
            audience=_TEST_AUDIENCE,
        )


def test_decode_invalid_audience_raises() -> None:
    token = _encode_token(_valid_payload(aud="other-audience"))
    with pytest.raises(InvalidAudienceError):
        decode_supabase_access_token(
            token,
            jwt_secret=_TEST_SECRET,
            audience=_TEST_AUDIENCE,
        )


def test_decode_malformed_token_raises() -> None:
    with pytest.raises(InvalidTokenError):
        decode_supabase_access_token(
            "not-a-valid-jwt",
            jwt_secret=_TEST_SECRET,
            audience=_TEST_AUDIENCE,
        )


def test_decode_missing_sub_raises() -> None:
    payload = _valid_payload()
    del payload["sub"]
    token = _encode_token(payload)
    with pytest.raises(MissingRequiredClaimError) as exc_info:
        decode_supabase_access_token(
            token,
            jwt_secret=_TEST_SECRET,
            audience=_TEST_AUDIENCE,
        )
    assert exc_info.value.claim == "sub"


def test_decode_missing_exp_raises() -> None:
    payload = _valid_payload()
    del payload["exp"]
    token = _encode_token(payload)
    with pytest.raises(MissingRequiredClaimError) as exc_info:
        decode_supabase_access_token(
            token,
            jwt_secret=_TEST_SECRET,
            audience=_TEST_AUDIENCE,
        )
    assert exc_info.value.claim == "exp"


def test_decode_missing_aud_raises() -> None:
    payload = _valid_payload()
    del payload["aud"]
    token = _encode_token(payload)
    with pytest.raises(MissingRequiredClaimError) as exc_info:
        decode_supabase_access_token(
            token,
            jwt_secret=_TEST_SECRET,
            audience=_TEST_AUDIENCE,
        )
    assert exc_info.value.claim == "aud"


def test_decode_respects_settings_audience_and_secret() -> None:
    settings = Settings(
        supabase_jwt_secret=_TEST_SECRET,
        supabase_jwt_audience=_TEST_AUDIENCE,
    )
    token = jwt.encode(
        _valid_payload(),
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )
    claims = decode_supabase_access_token(
        token,
        jwt_secret=settings.supabase_jwt_secret,
        audience=settings.supabase_jwt_audience,
    )
    assert claims["sub"] == "11111111-1111-1111-1111-111111111111"
