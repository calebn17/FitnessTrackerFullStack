"""Strava activities and OAuth HTTP routes."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.config import Settings, get_settings
from app.core.rate_limit import configured_read_limit, configured_write_limit, limiter
from app.dependencies import get_db_session, get_supabase_jwt_claims
from app.domains.activities.schemas import (
    ActivitiesRecentResponse,
    ActivitiesSummaryResponse,
    OAuthAuthorizeResponse,
    OAuthCallbackResponse,
)
from app.domains.activities.service import ActivityService
from app.domains.users.schemas import UserRead
from app.domains.users.service import UserService

router = APIRouter(tags=["activities"])


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


def _activity_service(
    session: AsyncSession,
    settings: Settings,
) -> ActivityService:
    return ActivityService(session, settings)


@router.get("/activities/recent", response_model=ActivitiesRecentResponse)
@limiter.limit(configured_read_limit)
async def activities_recent(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    sport_type: Annotated[str | None, Query()] = None,
) -> ActivitiesRecentResponse:
    user = await _current_user(claims, session)
    async with _activity_service(session, settings) as service:
        return await service.get_recent(
            user,
            limit=limit,
            sport_type=sport_type,
        )


@router.get("/activities/summary", response_model=ActivitiesSummaryResponse)
@limiter.limit(configured_read_limit)
async def activities_summary(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    period: Annotated[Literal["week", "month", "year"], Query()] = "week",
) -> ActivitiesSummaryResponse:
    user = await _current_user(claims, session)
    async with _activity_service(session, settings) as service:
        return await service.get_summary(user, period=period)


@router.get("/auth/strava/authorize", response_model=OAuthAuthorizeResponse)
@limiter.limit(configured_read_limit)
async def strava_authorize(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OAuthAuthorizeResponse:
    user = await _current_user(claims, session)
    async with _activity_service(session, settings) as service:
        return await service.build_authorize_url(user)


@router.get("/auth/strava/callback", response_model=OAuthCallbackResponse)
@limiter.limit(configured_write_limit)
async def strava_callback(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> OAuthCallbackResponse:
    await _current_user(claims, session)
    async with _activity_service(session, settings) as service:
        return await service.handle_callback(code=code, state=state)


@router.delete("/auth/strava/disconnect", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(configured_write_limit)
async def strava_disconnect(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    user = await _current_user(claims, session)
    async with _activity_service(session, settings) as service:
        await service.disconnect(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
