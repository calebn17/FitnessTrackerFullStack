"""HTTP middleware for request logging and metrics (Phase 7)."""

from __future__ import annotations

import time
import uuid
from typing import cast

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.config import Settings, get_settings
from app.core.logging import bind_request_context, get_logger, reset_request_context
from app.core.metrics import observe_request
from app.core.security import decode_supabase_access_token

_SKIP_METRICS_PATHS = frozenset({"/metrics"})
_UNMATCHED_ROUTE_LABEL = "<unmatched>"


def _effective_settings(request: Request) -> Settings:
    override = request.app.dependency_overrides.get(get_settings)
    if override is not None:
        return cast(Settings, override())
    return get_settings()


def _route_template(request: Request) -> str | None:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str):
        return path
    return None


def _try_supabase_sub(authorization: str | None, settings: Settings) -> str | None:
    if authorization is None or not authorization.strip():
        return None
    scheme, _, remainder = authorization.strip().partition(" ")
    if scheme.lower() != "bearer" or not remainder.strip():
        return None
    token = remainder.strip()
    if not settings.supabase_jwt_secret.strip():
        return None
    try:
        claims = decode_supabase_access_token(
            token,
            jwt_secret=settings.supabase_jwt_secret,
            audience=settings.supabase_jwt_audience,
        )
    except Exception:
        return None
    sub = claims.get("sub")
    return str(sub) if sub is not None else None


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    """Bind request context, log each HTTP request, and record Prometheus metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        raw_request_id = request.headers.get("x-request-id")
        request_id = (
            raw_request_id.strip()
            if raw_request_id and raw_request_id.strip()
            else str(uuid.uuid4())
        )
        settings = _effective_settings(request)
        user_sub = _try_supabase_sub(request.headers.get("authorization"), settings)

        bind_request_context(request_id=request_id)
        if user_sub is not None:
            bind_request_context(user_id=user_sub)

        log = get_logger(__name__)
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
                status_code = response.status_code
            except Exception as exc:
                # Starlette reports some ASGI short-circuit errors (e.g. route raises
                # asyncio.CancelledError with no HTTP response) as RuntimeError —
                # do not classify that sentinel as HTTP 500 in logs or metrics.
                if isinstance(exc, RuntimeError) and exc.args == ("No response returned.",):
                    raise exc
                duration_s = time.perf_counter() - start
                route = _route_template(request)
                duration_ms = round(duration_s * 1000, 3)
                log.info(
                    "http.request",
                    method=request.method,
                    path=request.url.path,
                    route=route or request.url.path,
                    status=500,
                    duration_ms=duration_ms,
                )
                if request.url.path not in _SKIP_METRICS_PATHS:
                    observe_request(
                        method=request.method,
                        route=route or _UNMATCHED_ROUTE_LABEL,
                        status_code=500,
                        duration_seconds=duration_s,
                    )
                raise

            duration_s = time.perf_counter() - start
            route = _route_template(request)
            duration_ms = round(duration_s * 1000, 3)
            log.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                route=route or request.url.path,
                status=status_code,
                duration_ms=duration_ms,
            )
            if request.url.path not in _SKIP_METRICS_PATHS:
                observe_request(
                    method=request.method,
                    route=route or _UNMATCHED_ROUTE_LABEL,
                    status_code=status_code,
                    duration_seconds=duration_s,
                )

            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            reset_request_context()
