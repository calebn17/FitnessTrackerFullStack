"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.core.database import dispose_engine
from app.core.logging import configure_logging
from app.core.metrics import render_metrics
from app.core.middleware import RequestObservabilityMiddleware
from app.dependencies import get_db_session
from app.domains.sync.router import router as sync_router
from app.domains.users.router import router as users_router
from app.domains.workouts.router import router as workouts_router


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
    application.add_middleware(RequestObservabilityMiddleware)

    application.include_router(users_router, prefix=settings.api_v1_prefix)
    application.include_router(workouts_router, prefix=settings.api_v1_prefix)
    application.include_router(sync_router, prefix=settings.api_v1_prefix)

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
