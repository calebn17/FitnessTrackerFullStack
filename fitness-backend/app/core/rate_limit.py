"""HTTP rate limiting (Phase 8) using SlowAPI."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

# Shared limiter instance; `app.state.limiter` must reference this object for SlowAPI.
limiter = Limiter(
    key_func=get_remote_address,
    headers_enabled=True,
)


def configured_read_limit(*_args: object, **_kwargs: object) -> str:
    """Return the current read-route limit from runtime settings."""
    return get_settings().rate_limit_read


def configured_write_limit(*_args: object, **_kwargs: object) -> str:
    """Return the current write-route limit from runtime settings."""
    return get_settings().rate_limit_write
