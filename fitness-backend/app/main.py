"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, cast

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse, Response

from app.config import Settings, get_settings
from app.core.database import dispose_engine
from app.core.logging import configure_logging
from app.core.metrics import render_metrics
from app.core.middleware import RequestObservabilityMiddleware
from app.core.rate_limit import limiter
from app.core.security_headers import SecurityHeadersMiddleware, apply_security_headers
from app.dependencies import get_db_session
from app.domains.activities.router import router as activities_router
from app.domains.health.router import router as health_router
from app.domains.sync.router import router as sync_router
from app.domains.users.router import router as users_router
from app.domains.workouts.router import router as workouts_router


def _settings_for_request(request: StarletteRequest) -> Settings:
    override = request.app.dependency_overrides.get(get_settings)
    if override is not None:
        return cast(Settings, override())
    return get_settings()


async def _unhandled_exception_handler(
    request: StarletteRequest, exc: Exception
) -> Response:
    if isinstance(exc, HTTPException):
        return await http_exception_handler(request, exc)
    if isinstance(exc, RequestValidationError):
        return await request_validation_exception_handler(request, exc)
    settings = _settings_for_request(request)
    if settings.debug:
        raise exc
    logging.exception("Unhandled server error", exc_info=exc)
    request_id = str(
        request.scope.get("request_id") or request.headers.get("x-request-id") or uuid.uuid4()
    ).strip()
    response = JSONResponse(
        status_code=500,
        headers={"X-Request-ID": request_id},
        content={
            "detail": {
                "code": "internal_server_error",
                "message": "Internal server error.",
            },
        },
    )
    apply_security_headers(response.headers, request.url.path)
    return response


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup/shutdown hooks (expand in later phases)."""
    try:
        yield
    finally:
        await dispose_engine()


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()
    configure_logging(debug=settings.debug)

    application = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        debug=settings.debug,
    )
    application.state.limiter = limiter
    application.add_exception_handler(
        RateLimitExceeded,
        cast(
            "Callable[[StarletteRequest, Exception], Awaitable[Response]]",
            _rate_limit_exceeded_handler,
        ),
    )
    application.add_exception_handler(Exception, _unhandled_exception_handler)
    application.add_middleware(RequestObservabilityMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.resolved_cors_origins(),
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(users_router, prefix=settings.api_v1_prefix)
    application.include_router(workouts_router, prefix=settings.api_v1_prefix)
    application.include_router(sync_router, prefix=settings.api_v1_prefix)
    application.include_router(activities_router, prefix=settings.api_v1_prefix)
    application.include_router(health_router, prefix=settings.api_v1_prefix)

    @application.get("/health")
    async def health(
        session: Annotated[AsyncSession, Depends(get_db_session)],
    ) -> JSONResponse:
        try:
            await session.execute(text("SELECT 1"))
        except Exception:
            checks = {"database": {"status": "error"}}
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "checks": checks},
            )
        checks = {"database": {"status": "ok"}}
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "checks": checks},
        )

    @application.get("/metrics")
    async def metrics() -> Response:
        body, media_type = render_metrics()
        return Response(content=body, media_type=media_type)

    return application


app = create_app()
