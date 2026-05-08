"""JWT validation and Supabase auth (implemented in Phase 3)."""

from typing import Any

import jwt


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
