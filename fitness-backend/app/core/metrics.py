"""Prometheus metrics (Phase 7)."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ("method", "route", "status_code"),
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


def observe_request(
    *,
    method: str,
    route: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record request count and latency."""
    labels = (method.upper(), route, str(status_code))
    REQUEST_COUNT.labels(*labels).inc()
    REQUEST_LATENCY.labels(method.upper(), route).observe(duration_seconds)


def render_metrics() -> tuple[bytes, str]:
    """Return Prometheus exposition body and content type."""
    return generate_latest(), CONTENT_TYPE_LATEST
