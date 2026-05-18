"""Unit tests for structured logging."""

from __future__ import annotations

import json

import pytest

from app.core import logging as logging_module


@pytest.fixture(autouse=True)
def _reset_logging() -> None:
    logging_module.reset_logging_configuration_for_tests()
    yield
    logging_module.reset_logging_configuration_for_tests()


def test_configure_logging_emits_json_with_required_fields(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logging_module.configure_logging(debug=False)
    log = logging_module.get_logger("test")
    logging_module.bind_request_context(request_id="req-123")
    log.info("http.request", method="GET", path="/health", status=200, duration_ms=1.5)
    logging_module.reset_request_context()

    captured = capsys.readouterr().out.strip()
    assert captured, "expected JSON log line on stdout"
    payload = json.loads(captured)
    assert payload["timestamp"]
    assert payload["level"] == "info"
    assert payload["event"] == "http.request"
    assert payload["request_id"] == "req-123"
    assert payload["method"] == "GET"
    assert payload["path"] == "/health"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 1.5
