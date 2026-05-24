"""JWT validation and Supabase auth (implemented in Phase 3)."""

from typing import Annotated, Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidSignatureError,
    InvalidTokenError,
    MissingRequiredClaimError,
)

from app.config import Settings, get_settings

_DEBUG_AUTH_TOKEN = "fitnesstracker-debug-user"
_DEBUG_USER_ID = "debug-user"


def decode_supabase_access_token(
    token: str,
    *,
    jwt_secret: str,
    audience: str,
) -> dict[str, Any]:
    """Decode and validate a Supabase-style HS256 access token.

    Raises PyJWT exceptions on failure; HTTP layers map these to 401 responses.
    """
    return jwt.decode(
        token,
        jwt_secret,
        algorithms=["HS256"],
        audience=audience,
        options={
            "require": ["exp", "sub", "aud"],
        },
    )


def _unauthorized(detail: dict[str, Any]) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _parse_bearer_token(authorization: str | None) -> str:
    if authorization is None or not authorization.strip():
        raise _unauthorized(
            {
                "code": "missing_authorization",
                "message": "Authorization header is missing.",
            },
        ) from None
    scheme, _, remainder = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not remainder.strip():
        raise _unauthorized(
            {
                "code": "invalid_authorization_format",
                "message": "Authorization header must be a Bearer token.",
            },
        ) from None
    return remainder.strip()


def get_supabase_jwt_claims(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict[str, Any]:
    """Decode the request Bearer token into Supabase JWT claims (or raise 401)."""
    raw = _parse_bearer_token(authorization)
    if settings.debug_auth_enabled and raw == _DEBUG_AUTH_TOKEN:
        return {
            "sub": _DEBUG_USER_ID,
            "aud": settings.supabase_jwt_audience,
        }
    if not settings.supabase_jwt_secret.strip():
        raise _unauthorized(
            {
                "code": "auth_not_configured",
                "message": "Server JWT validation is not configured.",
            },
        ) from None
    try:
        return decode_supabase_access_token(
            raw,
            jwt_secret=settings.supabase_jwt_secret,
            audience=settings.supabase_jwt_audience,
        )
    except ExpiredSignatureError as exc:
        raise _unauthorized(
            {
                "code": "token_expired",
                "message": "The access token has expired.",
            },
        ) from exc
    except InvalidAudienceError as exc:
        raise _unauthorized(
            {
                "code": "token_invalid_audience",
                "message": "The access token audience is invalid.",
            },
        ) from exc
    except InvalidSignatureError as exc:
        raise _unauthorized(
            {
                "code": "token_invalid_signature",
                "message": "The access token signature is invalid.",
            },
        ) from exc
    except MissingRequiredClaimError as exc:
        raise _unauthorized(
            {
                "code": "token_missing_claim",
                "message": "The access token is missing a required claim.",
                "claim": exc.claim,
            },
        ) from exc
    except InvalidTokenError as exc:
        raise _unauthorized(
            {
                "code": "token_invalid",
                "message": "The access token could not be validated.",
            },
        ) from exc
