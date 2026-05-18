"""Unit tests for Prometheus metrics helpers."""

from __future__ import annotations

from prometheus_client import REGISTRY

from app.core.metrics import observe_request, render_metrics


def test_observe_request_increments_counter_and_histogram() -> None:
    route = "/__metrics_test_route__"
    before = REGISTRY.get_sample_value(
        "http_requests_total",
        {"method": "GET", "route": route, "status_code": "200"},
    ) or 0.0
    observe_request(method="GET", route=route, status_code=200, duration_seconds=0.01)
    after = REGISTRY.get_sample_value(
        "http_requests_total",
        {"method": "GET", "route": route, "status_code": "200"},
    )
    assert after == before + 1.0

    body, content_type = render_metrics()
    assert content_type
    text = body.decode("utf-8")
    assert "http_requests_total" in text
    assert "http_request_duration_seconds" in text
