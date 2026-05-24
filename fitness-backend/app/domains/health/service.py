"""Whoop sync, OAuth, and health read logic."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
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
    exchange_whoop_code,
    oauth_state_store,
    refresh_whoop_token,
)
from app.domains.activities.models import PROVIDER_WHOOP, OAuthToken
from app.domains.activities.repository import OAuthTokenRepository
from app.domains.activities.schemas import OAuthAuthorizeResponse, OAuthCallbackResponse
from app.domains.health.models import PROVIDER_WHOOP as HEALTH_PROVIDER_WHOOP
from app.domains.health.repository import DailyHealthRepository
from app.domains.health.schemas import (
    DailyHealthRead,
    HealthRecentResponse,
    HealthSummaryResponse,
    HealthTodayResponse,
    normalize_whoop_day,
)
from app.domains.health.whoop_client import (
    WhoopApiError,
    WhoopClient,
    WhoopRateLimitedError,
    cycle_calendar_date,
    index_by_cycle_id,
    index_sleep_by_cycle,
)
from app.domains.users.schemas import UserRead

WHOOP_AUTHORIZE_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_SCOPE = "read:cycles read:recovery read:sleep read:workout read:profile offline"


class HealthService:
    """Coordinates Whoop OAuth, sync, and health reads."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        *,
        whoop_client: WhoopClient | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._tokens = OAuthTokenRepository(session)
        self._health = DailyHealthRepository(session)
        self._whoop = whoop_client or WhoopClient()

    async def __aenter__(self) -> HealthService:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._whoop.aclose()

    def _require_whoop_config(self) -> None:
        if not self._settings.whoop_configured():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "provider_not_configured",
                    "message": "Whoop OAuth credentials are not configured.",
                },
            )

    def _whoop_refresh_config(self) -> OAuthRefreshConfig:
        return OAuthRefreshConfig(
            token_url="https://api.prod.whoop.com/oauth/oauth2/token",
            client_id=self._settings.whoop_client_id,
            client_secret=self._settings.whoop_client_secret,
        )

    async def build_authorize_url(self, user: UserRead) -> OAuthAuthorizeResponse:
        self._require_whoop_config()
        state = oauth_state_store.create(user.id)
        params = {
            "client_id": self._settings.whoop_client_id,
            "response_type": "code",
            "redirect_uri": self._settings.whoop_redirect_uri,
            "scope": WHOOP_SCOPE,
            "state": state,
        }
        url = f"{WHOOP_AUTHORIZE_URL}?{urlencode(params)}"
        return OAuthAuthorizeResponse(authorization_url=url)

    async def handle_callback(self, *, code: str, state: str) -> OAuthCallbackResponse:
        self._require_whoop_config()
        try:
            user_id = oauth_state_store.consume(state)
        except OAuthStateError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "invalid_oauth_state", "message": str(exc)},
            ) from exc
        try:
            payload = await exchange_whoop_code(
                code=code,
                client_id=self._settings.whoop_client_id,
                client_secret=self._settings.whoop_client_secret,
                redirect_uri=self._settings.whoop_redirect_uri,
            )
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"code": "provider_token_exchange_failed", "message": str(exc)},
            ) from exc
        await self._tokens.upsert(
            user_id=user_id,
            provider=PROVIDER_WHOOP,
            access_token=payload.access_token,
            refresh_token=payload.refresh_token,
            expires_at=payload.expires_at,
            athlete_id=payload.athlete_id,
            scopes=payload.scopes,
        )
        await self._session.commit()
        return OAuthCallbackResponse(provider=PROVIDER_WHOOP)

    async def disconnect(self, user: UserRead) -> None:
        token = await self._tokens.get_for_user_provider(user.id, PROVIDER_WHOOP)
        if token is None:
            return
        try:
            await self._whoop.revoke_token(
                token=token.refresh_token,
                client_id=self._settings.whoop_client_id,
                client_secret=self._settings.whoop_client_secret,
            )
        except WhoopApiError:
            pass
        await self._tokens.delete_for_user_provider(user.id, PROVIDER_WHOOP)
        await self._session.commit()

    async def _get_valid_whoop_token(self, user_id: uuid.UUID) -> OAuthToken:
        token = await self._tokens.get_for_user_provider(user_id, PROVIDER_WHOOP)
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "provider_not_connected",
                    "message": "Whoop is not connected for this user.",
                },
            )
        try:
            return await ensure_valid_token(
                token,
                self._whoop_refresh_config(),
                self._session,
                refresh_fn=refresh_whoop_token,
            )
        except ProviderAuthExpiredError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "provider_auth_expired",
                    "message": "Whoop authorization has expired. Please reconnect.",
                },
            ) from exc

    def _is_stale(self, token: OAuthToken) -> bool:
        if token.last_synced_at is None:
            return True
        threshold = timedelta(minutes=self._settings.sync_staleness_minutes)
        return datetime.now(UTC) - token.last_synced_at > threshold

    async def sync_if_stale(self, user_id: uuid.UUID) -> datetime | None:
        token = await self._get_valid_whoop_token(user_id)
        if not self._is_stale(token):
            return token.last_synced_at
        try:
            await self._sync_health(user_id, token)
            await self._tokens.touch_last_synced(token)
            await self._session.commit()
            await self._session.refresh(token)
            return token.last_synced_at
        except ProviderAuthExpiredError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "provider_auth_expired",
                    "message": "Whoop authorization has expired. Please reconnect.",
                },
            ) from exc
        except (WhoopRateLimitedError, WhoopApiError):
            await self._session.rollback()
            return token.last_synced_at

    async def _sync_health(self, user_id: uuid.UUID, token: OAuthToken) -> None:
        end = datetime.now(UTC)
        if token.last_synced_at is not None:
            start = token.last_synced_at
        else:
            start = end - timedelta(days=90)
        cycles = await self._whoop.list_cycles(token.access_token, start=start, end=end)
        sleep_rows = await self._whoop.list_sleep(token.access_token, start=start, end=end)
        recovery_rows = await self._whoop.list_recovery(token.access_token, start=start, end=end)
        recovery_by_cycle = index_by_cycle_id(recovery_rows)
        sleep_by_cycle = index_sleep_by_cycle(sleep_rows)
        for cycle in cycles:
            if cycle.get("score_state") != "SCORED":
                continue
            record_date = cycle_calendar_date(cycle)
            if record_date is None:
                continue
            cycle_id = cycle.get("id")
            sleep = sleep_by_cycle.get(int(cycle_id)) if cycle_id is not None else None
            recovery = recovery_by_cycle.get(int(cycle_id)) if cycle_id is not None else None
            normalized = normalize_whoop_day(
                record_date=record_date,
                cycle=cycle,
                sleep=sleep,
                recovery=recovery,
            )
            await self._health.upsert_record(
                user_id=user_id,
                values=normalized.model_dump(),
            )

    async def get_today(self, user: UserRead) -> HealthTodayResponse:
        synced_at = await self.sync_if_stale(user.id)
        record = await self._health.get_for_date(
            user.id,
            date.today(),
            provider=HEALTH_PROVIDER_WHOOP,
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "no_health_data",
                    "message": "No health data for today.",
                },
            )
        payload = DailyHealthRead.from_record(record, synced_at=synced_at)
        return HealthTodayResponse(**payload.model_dump())

    async def get_recent(self, user: UserRead, *, days: int = 7) -> HealthRecentResponse:
        synced_at = await self.sync_if_stale(user.id)
        rows = await self._health.list_recent(
            user.id,
            days=min(days, 90),
            provider=HEALTH_PROVIDER_WHOOP,
        )
        return HealthRecentResponse(
            records=[DailyHealthRead.from_record(r, synced_at=synced_at) for r in rows],
            synced_at=synced_at,
        )

    async def get_summary(self, user: UserRead, *, days: int = 30) -> HealthSummaryResponse:
        synced_at = await self.sync_if_stale(user.id)
        bounded_days = min(days, 365)
        agg = await self._health.aggregate_summary(
            user.id,
            days=bounded_days,
            provider=HEALTH_PROVIDER_WHOOP,
        )
        avg_sleep_hours = None
        if agg["avg_total_sleep"] is not None:
            avg_sleep_hours = round(agg["avg_total_sleep"] / 3600.0, 1)
        return HealthSummaryResponse(
            period_days=bounded_days,
            actual_days_with_data=agg["actual_days"],
            provider=HEALTH_PROVIDER_WHOOP,
            avg_sleep_score=round(agg["avg_sleep_score"], 1) if agg["avg_sleep_score"] else None,
            avg_total_sleep_hours=avg_sleep_hours,
            avg_recovery_score=round(agg["avg_recovery"], 1) if agg["avg_recovery"] else None,
            avg_resting_heart_rate=round(agg["avg_rhr"], 1) if agg["avg_rhr"] else None,
            avg_hrv=round(agg["avg_hrv"], 1) if agg["avg_hrv"] else None,
            avg_strain_score=round(agg["avg_strain"], 1) if agg["avg_strain"] else None,
            avg_active_calories=round(agg["avg_active_cal"], 1) if agg["avg_active_cal"] else None,
            synced_at=synced_at,
        )
