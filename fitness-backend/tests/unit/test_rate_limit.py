"""Unit tests for SlowAPI limiter wiring."""

from app.core.rate_limit import limiter
from app.main import create_app


def test_create_app_registers_limiter_on_state() -> None:
    app = create_app()
    assert app.state.limiter is limiter
