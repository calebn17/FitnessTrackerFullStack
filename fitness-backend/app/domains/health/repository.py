"""Persistence for daily health records and OAuth tokens."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.repository import BaseRepository
from app.domains.activities.repository import OAuthTokenRepository
from app.domains.health.models import DailyHealthRecord

__all__ = ["DailyHealthRepository", "OAuthTokenRepository"]


class DailyHealthRepository(BaseRepository):
    """Daily wearable health record access."""

    async def upsert_record(
        self,
        *,
        user_id: uuid.UUID,
        values: dict[str, Any],
    ) -> DailyHealthRecord:
        now = datetime.now(UTC)
        insert_stmt = insert(DailyHealthRecord).values(
            user_id=user_id,
            created_at=now,
            updated_at=now,
            **values,
        )
        excluded = insert_stmt.excluded
        update_fields = {
            key: getattr(excluded, key)
            for key in values
            if key not in ("date", "provider")
        }
        update_fields["updated_at"] = now
        stmt = insert_stmt.on_conflict_do_update(
            index_elements=["user_id", "date", "provider"],
            set_=update_fields,
        ).returning(DailyHealthRecord)
        result = await self.session.execute(stmt)
        row = result.scalar_one()
        await self.session.flush()
        return row

    async def get_for_date(
        self,
        user_id: uuid.UUID,
        record_date: date,
        *,
        provider: str,
    ) -> DailyHealthRecord | None:
        stmt = select(DailyHealthRecord).where(
            DailyHealthRecord.user_id == user_id,
            DailyHealthRecord.date == record_date,
            DailyHealthRecord.provider == provider,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(
        self,
        user_id: uuid.UUID,
        *,
        days: int,
        provider: str,
    ) -> list[DailyHealthRecord]:
        start = date.today() - timedelta(days=days - 1)
        stmt = (
            select(DailyHealthRecord)
            .where(
                DailyHealthRecord.user_id == user_id,
                DailyHealthRecord.provider == provider,
                DailyHealthRecord.date >= start,
            )
            .order_by(DailyHealthRecord.date.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def aggregate_summary(
        self,
        user_id: uuid.UUID,
        *,
        days: int,
        provider: str,
    ) -> dict[str, Any]:
        start = date.today() - timedelta(days=days - 1)
        stmt = (
            select(
                func.count().label("actual_days"),
                func.avg(DailyHealthRecord.sleep_score).label("avg_sleep_score"),
                func.avg(DailyHealthRecord.total_sleep_seconds).label("avg_total_sleep"),
                func.avg(DailyHealthRecord.recovery_score).label("avg_recovery"),
                func.avg(DailyHealthRecord.resting_heart_rate).label("avg_rhr"),
                func.avg(DailyHealthRecord.hrv).label("avg_hrv"),
                func.avg(DailyHealthRecord.strain_score).label("avg_strain"),
                func.avg(DailyHealthRecord.active_calories).label("avg_active_cal"),
            )
            .where(
                DailyHealthRecord.user_id == user_id,
                DailyHealthRecord.provider == provider,
                DailyHealthRecord.date >= start,
            )
        )
        result = await self.session.execute(stmt)
        row = result.one()
        return {
            "actual_days": int(row.actual_days or 0),
            "avg_sleep_score": float(row.avg_sleep_score) if row.avg_sleep_score else None,
            "avg_total_sleep": float(row.avg_total_sleep) if row.avg_total_sleep else None,
            "avg_recovery": float(row.avg_recovery) if row.avg_recovery else None,
            "avg_rhr": float(row.avg_rhr) if row.avg_rhr else None,
            "avg_hrv": float(row.avg_hrv) if row.avg_hrv else None,
            "avg_strain": float(row.avg_strain) if row.avg_strain else None,
            "avg_active_cal": float(row.avg_active_cal) if row.avg_active_cal else None,
        }
