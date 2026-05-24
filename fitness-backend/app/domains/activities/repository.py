"""Persistence for Strava activities and OAuth tokens."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.repository import BaseRepository
from app.domains.activities.models import OAuthToken, StravaActivity

RUNNING_SPORT_TYPES = ("Run", "TrailRun", "VirtualRun")


class OAuthTokenRepository(BaseRepository):
    """OAuth token storage."""

    async def get_for_user_provider(
        self,
        user_id: uuid.UUID,
        provider: str,
    ) -> OAuthToken | None:
        stmt = (
            select(OAuthToken)
            .where(
                OAuthToken.user_id == user_id,
                OAuthToken.provider == provider,
            )
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        access_token: str,
        refresh_token: str,
        expires_at: datetime,
        athlete_id: str | None = None,
        scopes: str | None = None,
    ) -> OAuthToken:
        now = datetime.now(UTC)
        insert_stmt = insert(OAuthToken).values(
            user_id=user_id,
            provider=provider,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            athlete_id=athlete_id,
            scopes=scopes,
            created_at=now,
            updated_at=now,
        )
        excluded = insert_stmt.excluded
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["user_id", "provider"],
            set_={
                "access_token": excluded.access_token,
                "refresh_token": excluded.refresh_token,
                "expires_at": excluded.expires_at,
                "athlete_id": excluded.athlete_id,
                "scopes": excluded.scopes,
                "updated_at": now,
            },
        ).returning(OAuthToken)
        result = await self.session.execute(stmt)
        token = result.scalar_one()
        await self.session.flush()
        await self.session.refresh(token)
        return token

    async def delete_for_user_provider(self, user_id: uuid.UUID, provider: str) -> bool:
        token = await self.get_for_user_provider(user_id, provider)
        if token is None:
            return False
        await self.session.delete(token)
        await self.session.flush()
        return True

    async def touch_last_synced(self, token: OAuthToken, *, when: datetime | None = None) -> None:
        token.last_synced_at = when or datetime.now(UTC)
        token.updated_at = datetime.now(UTC)
        await self.session.flush()


class StravaActivityRepository(BaseRepository):
    """Strava activity queries and upserts."""

    def _running_filter(self, stmt: Select[Any], sport_type: str | None) -> Select[Any]:
        if sport_type is not None:
            return stmt.where(StravaActivity.sport_type == sport_type)
        return stmt.where(StravaActivity.sport_type.in_(RUNNING_SPORT_TYPES))

    async def upsert_activity(
        self,
        *,
        user_id: uuid.UUID,
        values: dict[str, Any],
    ) -> StravaActivity:
        now = datetime.now(UTC)
        insert_stmt = insert(StravaActivity).values(user_id=user_id, created_at=now, **values)
        excluded = insert_stmt.excluded
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["strava_id"],
            set_={key: getattr(excluded, key) for key in values if key != "strava_id"},
        ).returning(StravaActivity)
        result = await self.session.execute(stmt)
        row = result.scalar_one()
        await self.session.flush()
        return row

    async def list_recent(
        self,
        user_id: uuid.UUID,
        *,
        limit: int = 10,
        sport_type: str | None = None,
    ) -> list[StravaActivity]:
        stmt = select(StravaActivity).where(StravaActivity.user_id == user_id)
        stmt = self._running_filter(stmt, sport_type)
        stmt = stmt.order_by(StravaActivity.start_date_local.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def aggregate_summary(
        self,
        user_id: uuid.UUID,
        *,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        stmt = (
            select(
                func.count().label("total_runs"),
                func.coalesce(func.sum(StravaActivity.distance), 0.0).label("total_distance"),
                func.coalesce(func.sum(StravaActivity.moving_time), 0).label("total_moving_time"),
                func.coalesce(func.sum(StravaActivity.calories), 0.0).label("total_calories"),
                func.coalesce(func.sum(StravaActivity.total_elevation_gain), 0.0).label(
                    "total_elevation"
                ),
            )
            .where(
                StravaActivity.user_id == user_id,
                StravaActivity.sport_type.in_(RUNNING_SPORT_TYPES),
                func.date(StravaActivity.start_date_local) >= start_date,
                func.date(StravaActivity.start_date_local) <= end_date,
            )
        )
        result = await self.session.execute(stmt)
        row = result.one()
        return {
            "total_runs": int(row.total_runs),
            "total_distance": float(row.total_distance),
            "total_moving_time": int(row.total_moving_time),
            "total_calories": float(row.total_calories) if row.total_calories else None,
            "total_elevation": float(row.total_elevation),
        }

    async def run_dates_for_streak(self, user_id: uuid.UUID) -> list[date]:
        stmt = (
            select(func.date(StravaActivity.start_date_local).label("run_date"))
            .where(
                StravaActivity.user_id == user_id,
                StravaActivity.sport_type.in_(RUNNING_SPORT_TYPES),
            )
            .distinct()
            .order_by(func.date(StravaActivity.start_date_local).desc())
        )
        result = await self.session.execute(stmt)
        return [row.run_date for row in result.all()]
