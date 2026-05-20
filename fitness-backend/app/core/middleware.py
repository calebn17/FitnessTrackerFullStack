"""HTTP middleware for request logging and metrics (Phase 7)."""

from __future__ import annotations

import time
import uuid
from typing import cast

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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


class RequestObservabilityMiddleware:
    """Bind request context, log each HTTP request, and record Prometheus metrics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        raw_request_id = request.headers.get("x-request-id")
        request_id = (
            raw_request_id.strip()
            if raw_request_id and raw_request_id.strip()
            else str(uuid.uuid4())
        )
        scope["request_id"] = request_id
        settings = _effective_settings(request)
        user_sub = _try_supabase_sub(request.headers.get("authorization"), settings)

        bind_request_context(request_id=request_id)
        if user_sub is not None:
            bind_request_context(user_id=user_sub)

        log = get_logger(__name__)
        start = time.perf_counter()
        status_code: int | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(raw=list(message["headers"]))
                headers["X-Request-ID"] = request_id
                message = {**message, "headers": headers.raw}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if isinstance(exc, RuntimeError) and exc.args == ("No response returned.",):
                raise
            duration_s = time.perf_counter() - start
            route = _route_template(request)
            duration_ms = round(duration_s * 1000, 3)
            code = status_code if status_code is not None else 500
            log.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                route=route or request.url.path,
                status=code,
                duration_ms=duration_ms,
            )
            if request.url.path not in _SKIP_METRICS_PATHS:
                observe_request(
                    method=request.method,
                    route=route or _UNMATCHED_ROUTE_LABEL,
                    status_code=code,
                    duration_seconds=duration_s,
                )
            raise
        else:
            duration_s = time.perf_counter() - start
            route = _route_template(request)
            duration_ms = round(duration_s * 1000, 3)
            code = status_code if status_code is not None else 200
            log.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                route=route or request.url.path,
                status=code,
                duration_ms=duration_ms,
            )
            if request.url.path not in _SKIP_METRICS_PATHS:
                observe_request(
                    method=request.method,
                    route=route or _UNMATCHED_ROUTE_LABEL,
                    status_code=code,
                    duration_seconds=duration_s,
                )
        finally:
            reset_request_context()
