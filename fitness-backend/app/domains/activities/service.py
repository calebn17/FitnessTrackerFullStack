"""Strava sync, OAuth, and activity read logic."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.oauth import (
    OAuthRefreshConfig,
    OAuthStateError,
    ProviderAuthExpiredError,
    ensure_valid_token,
    exchange_strava_code,
    oauth_state_store,
    refresh_strava_token,
)
from app.domains.activities.models import PROVIDER_STRAVA, OAuthToken
from app.domains.activities.repository import OAuthTokenRepository, StravaActivityRepository
from app.domains.activities.schemas import (
    METERS_PER_FOOT,
    METERS_PER_MILE,
    ActivitiesRecentResponse,
    ActivitiesSummaryResponse,
    OAuthAuthorizeResponse,
    OAuthCallbackResponse,
    StravaActivityRead,
)
from app.domains.activities.strava_client import (
    StravaApiError,
    StravaClient,
    StravaRateLimitedError,
    parse_strava_activity,
)
from app.domains.users.schemas import UserRead

STRAVA_AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
STRAVA_SCOPE = "activity:read_all"


def _compute_streak(run_dates: list[date]) -> int:
    if not run_dates:
        return 0
    dates_set = set(run_dates)
    streak = 0
    cursor = date.today()
    while cursor in dates_set:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _period_bounds(period: Literal["week", "month", "year"]) -> tuple[date, date]:
    end = date.today()
    if period == "week":
        start = end - timedelta(days=7)
    elif period == "month":
        start = end - timedelta(days=30)
    else:
        start = end - timedelta(days=365)
    return start, end


class ActivityService:
    """Coordinates Strava OAuth, sync, and activity reads."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        strava_client: StravaClient | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._tokens = OAuthTokenRepository(session)
        self._activities = StravaActivityRepository(session)
        self._strava = strava_client or StravaClient()

    async def __aenter__(self) -> ActivityService:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._strava.aclose()

    def _require_strava_config(self) -> None:
        if not self._settings.strava_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "provider_not_configured",
                    "message": "Strava OAuth credentials are not configured.",
                },
            )

    def _strava_refresh_config(self) -> OAuthRefreshConfig:
        return OAuthRefreshConfig(
            token_url="https://www.strava.com/api/v3/oauth/token",
            client_id=self._settings.strava_client_id,
            client_secret=self._settings.strava_client_secret,
        )

    async def build_authorize_url(self, user: UserRead) -> OAuthAuthorizeResponse:
        self._require_strava_config()
        state = oauth_state_store.create(user.id)
        params = {
            "client_id": self._settings.strava_client_id,
            "response_type": "code",
            "redirect_uri": self._settings.strava_redirect_uri,
            "approval_prompt": "auto",
            "scope": STRAVA_SCOPE,
            "state": state,
        }
        url = f"{STRAVA_AUTHORIZE_URL}?{urlencode(params)}"
        return OAuthAuthorizeResponse(authorization_url=url)

    async def handle_callback(self, *, code: str, state: str) -> OAuthCallbackResponse:
        self._require_strava_config()
        try:
            user_id = oauth_state_store.consume(state)
        except OAuthStateError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_oauth_state", "message": str(exc)},
            ) from exc
        try:
            payload = await exchange_strava_code(
                code=code,
                client_id=self._settings.strava_client_id,
                client_secret=self._settings.strava_client_secret,
                redirect_uri=self._settings.strava_redirect_uri,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "provider_token_exchange_failed", "message": str(exc)},
            ) from exc
        await self._tokens.upsert(
            user_id=user_id,
            provider=PROVIDER_STRAVA,
            access_token=payload.access_token,
            refresh_token=payload.refresh_token,
            expires_at=payload.expires_at,
            athlete_id=payload.athlete_id,
            scopes=payload.scopes,
        )
        await self._session.commit()
        return OAuthCallbackResponse(provider=PROVIDER_STRAVA)

    async def disconnect(self, user: UserRead) -> None:
        token = await self._tokens.get_for_user_provider(user.id, PROVIDER_STRAVA)
        if token is None:
            return
        try:
            await self._strava.deauthorize(token.access_token)
        except StravaApiError:
            pass
        await self._tokens.delete_for_user_provider(user.id, PROVIDER_STRAVA)
        await self._session.commit()

    async def _get_valid_strava_token(self, user_id: uuid.UUID) -> OAuthToken:
        token = await self._tokens.get_for_user_provider(user_id, PROVIDER_STRAVA)
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "provider_not_connected",
                    "message": "Strava is not connected for this user.",
                },
            )
        try:
            return await ensure_valid_token(
                token,
                self._strava_refresh_config(),
                self._session,
                refresh_fn=refresh_strava_token,
            )
        except ProviderAuthExpiredError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "provider_auth_expired",
                    "message": "Strava authorization has expired. Please reconnect.",
                },
            ) from exc

    def _is_stale(self, token: OAuthToken) -> bool:
        if token.last_synced_at is None:
            return True
        threshold = timedelta(minutes=self._settings.sync_staleness_minutes)
        return datetime.now(UTC) - token.last_synced_at > threshold

    async def sync_if_stale(self, user_id: uuid.UUID) -> datetime | None:
        """Sync Strava activities when stale; returns last_synced_at (may be stale on errors)."""
        token = await self._get_valid_strava_token(user_id)
        if not self._is_stale(token):
            return token.last_synced_at
        try:
            await self._sync_activities(user_id, token)
            await self._tokens.touch_last_synced(token)
            await self._session.commit()
            await self._session.refresh(token)
            return token.last_synced_at
        except ProviderAuthExpiredError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "provider_auth_expired",
                    "message": "Strava authorization has expired. Please reconnect.",
                },
            ) from exc
        except (StravaRateLimitedError, StravaApiError):
            await self._session.rollback()
            return token.last_synced_at

    async def _sync_activities(self, user_id: uuid.UUID, token: OAuthToken) -> None:
        after: int | None = None
        if token.last_synced_at is not None:
            after = int(token.last_synced_at.timestamp())
        raw_items = await self._strava.fetch_all_running_activities(
            token.access_token,
            after=after,
        )
        for raw in raw_items:
            values = parse_strava_activity(raw)
            await self._activities.upsert_activity(user_id=user_id, values=values)

    async def get_recent(
        self,
        user: UserRead,
        *,
        limit: int = 10,
        sport_type: str | None = None,
    ) -> ActivitiesRecentResponse:
        synced_at = await self.sync_if_stale(user.id)
        rows = await self._activities.list_recent(
            user.id,
            limit=min(limit, 50),
            sport_type=sport_type,
        )
        return ActivitiesRecentResponse(
            activities=[StravaActivityRead.from_model(r) for r in rows],
            synced_at=synced_at,
        )

    async def get_summary(
        self,
        user: UserRead,
        *,
        period: Literal["week", "month", "year"] = "week",
    ) -> ActivitiesSummaryResponse:
        synced_at = await self.sync_if_stale(user.id)
        start_date, end_date = _period_bounds(period)
        agg = await self._activities.aggregate_summary(
            user.id,
            start_date=start_date,
            end_date=end_date,
        )
        total_distance_miles = round(agg["total_distance"] / METERS_PER_MILE, 2)
        total_moving = agg["total_moving_time"]
        avg_pace: float | None = None
        if total_distance_miles > 0 and total_moving > 0:
            avg_pace = round((total_moving / 60.0) / total_distance_miles, 2)
        run_dates = await self._activities.run_dates_for_streak(user.id)
        return ActivitiesSummaryResponse(
            period=period,
            start_date=start_date,
            end_date=end_date,
            total_runs=agg["total_runs"],
            total_distance_miles=total_distance_miles,
            total_moving_time_seconds=total_moving,
            average_pace_min_per_mile=avg_pace,
            total_elevation_gain_feet=round(agg["total_elevation"] / METERS_PER_FOOT, 1),
            total_calories=agg["total_calories"],
            streak_days=_compute_streak(run_dates),
            synced_at=synced_at,
        )
