"""Unit tests for observability middleware."""

from __future__ import annotations

import asyncio
import concurrent.futures
import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.core import logging as logging_module
from app.core.middleware import RequestObservabilityMiddleware


@pytest.fixture(autouse=True)
def _rebind_structlog_for_print_logger() -> Iterator[None]:
    """Avoid pytest-close stdout wrappers held by PrintLoggerFactory from earlier imports."""
    logging_module.reset_logging_configuration_for_tests()
    logging_module.configure_logging(debug=True)
    yield


def _metric_value(route: str, status_code: str) -> float:
    return (
        REGISTRY.get_sample_value(
            "http_requests_total",
            {"method": "GET", "route": route, "status_code": status_code},
        )
        or 0.0
    )


def test_unmatched_routes_use_bounded_metrics_label() -> None:
    app = FastAPI()
    app.add_middleware(RequestObservabilityMiddleware)
    client = TestClient(app)
    raw_path = f"/not-found/{uuid.uuid4()}"

    unmatched_before = _metric_value("<unmatched>", "404")
    raw_before = _metric_value(raw_path, "404")
    response = client.get(raw_path)

    assert response.status_code == 404
    assert _metric_value("<unmatched>", "404") == unmatched_before + 1.0
    assert _metric_value(raw_path, "404") == raw_before


def test_starlette_missing_response_skips_http_500_metrics() -> None:
    """Cancelled routes must not be counted as HTTP 500 in metrics.

    With Starlette's legacy BaseHTTPMiddleware, cancellation could surface as
    RuntimeError(\"No response returned.\"). Pure ASGI middleware lets
    asyncio.CancelledError propagate instead; both must skip the 500 counter.
    """
    app = FastAPI()
    app.add_middleware(RequestObservabilityMiddleware)

    @app.get("/cancel")
    async def cancel() -> None:
        raise asyncio.CancelledError

    client = TestClient(app)
    before = _metric_value("/cancel", "500")

    with pytest.raises(
        (RuntimeError, asyncio.CancelledError, concurrent.futures.CancelledError),
    ):
        client.get("/cancel")

    assert _metric_value("/cancel", "500") == before
