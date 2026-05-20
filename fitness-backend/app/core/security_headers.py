"""Security-related HTTP response headers (Phase 8)."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def apply_security_headers(headers: MutableHeaders, path: str) -> None:
    """Apply baseline security headers in-place."""
    if "x-content-type-options" not in headers:
        headers["X-Content-Type-Options"] = "nosniff"
    if "x-frame-options" not in headers:
        headers["X-Frame-Options"] = "DENY"
    if "referrer-policy" not in headers:
        headers["Referrer-Policy"] = "no-referrer"
    if path.startswith("/api/v1") and "cache-control" not in headers:
        headers["Cache-Control"] = "no-store"


class SecurityHeadersMiddleware:
    """Add baseline security headers to every response (pure ASGI; avoids BaseHTTPMiddleware)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "") or ""

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=list(message["headers"]))
                apply_security_headers(headers, path)
                message = {**message, "headers": headers.raw}
            await send(message)

        await self.app(scope, receive, send_wrapper)
