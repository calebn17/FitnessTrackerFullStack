"""Whoop health and OAuth HTTP routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.config import Settings, get_settings
from app.core.rate_limit import configured_read_limit, configured_write_limit, limiter
from app.dependencies import get_db_session, get_supabase_jwt_claims
from app.domains.activities.schemas import OAuthAuthorizeResponse, OAuthCallbackResponse
from app.domains.health.schemas import (
    HealthRecentResponse,
    HealthSummaryResponse,
    HealthTodayResponse,
)
from app.domains.health.service import HealthService
from app.domains.users.schemas import UserRead
from app.domains.users.service import UserService

router = APIRouter(tags=["health"])


async def _current_user(
    claims: dict[str, Any],
    session: AsyncSession,
) -> UserRead:
    try:
        user = await UserService(session).get_or_create_from_supabase(claims)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_user_claims", "errors": exc.errors()},
        ) from exc
    return UserRead.model_validate(user)


def _health_service(session: AsyncSession, settings: Settings) -> HealthService:
    return HealthService(session, settings)


@router.get("/health/today", response_model=HealthTodayResponse)
@limiter.limit(configured_read_limit)
async def health_today(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthTodayResponse:
    user = await _current_user(claims, session)
    async with _health_service(session, settings) as service:
        return await service.get_today(user)


@router.get("/health/recent", response_model=HealthRecentResponse)
@limiter.limit(configured_read_limit)
async def health_recent(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> HealthRecentResponse:
    user = await _current_user(claims, session)
    async with _health_service(session, settings) as service:
        return await service.get_recent(user, days=days)


@router.get("/health/summary", response_model=HealthSummaryResponse)
@limiter.limit(configured_read_limit)
async def health_summary(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> HealthSummaryResponse:
    user = await _current_user(claims, session)
    async with _health_service(session, settings) as service:
        return await service.get_summary(user, days=days)


@router.get("/auth/whoop/authorize", response_model=OAuthAuthorizeResponse)
@limiter.limit(configured_read_limit)
async def whoop_authorize(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OAuthAuthorizeResponse:
    user = await _current_user(claims, session)
    async with _health_service(session, settings) as service:
        return await service.build_authorize_url(user)


@router.get("/auth/whoop/callback", response_model=OAuthCallbackResponse)
@limiter.limit(configured_write_limit)
async def whoop_callback(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> OAuthCallbackResponse:
    await _current_user(claims, session)
    async with _health_service(session, settings) as service:
        return await service.handle_callback(code=code, state=state)


@router.delete("/auth/whoop/disconnect", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(configured_write_limit)
async def whoop_disconnect(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    user = await _current_user(claims, session)
    async with _health_service(session, settings) as service:
        await service.disconnect(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
