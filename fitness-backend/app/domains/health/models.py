"""SQLAlchemy models for daily wearable health records."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.activities.models import OAuthToken  # noqa: F401 — shared token table

PROVIDER_WHOOP = "whoop"
PROVIDER_OURA = "oura"


class DailyHealthRecord(Base):
    """Normalized daily health metrics from a wearable provider."""

    __tablename__ = "daily_health_records"
    __table_args__ = (
        UniqueConstraint("user_id", "date", "provider", name="uq_daily_health_user_date_provider"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    date: Mapped[date] = mapped_column(Date(), nullable=False)
    provider: Mapped[str] = mapped_column(String(), nullable=False)
    sleep_score: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    total_sleep_seconds: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    deep_sleep_seconds: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    rem_sleep_seconds: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    light_sleep_seconds: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    sleep_efficiency: Mapped[float | None] = mapped_column(Float(), nullable=True)
    recovery_score: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    resting_heart_rate: Mapped[float | None] = mapped_column(Float(), nullable=True)
    hrv: Mapped[float | None] = mapped_column(Float(), nullable=True)
    spo2: Mapped[float | None] = mapped_column(Float(), nullable=True)
    strain_score: Mapped[float | None] = mapped_column(Float(), nullable=True)
    active_calories: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    total_calories: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    steps: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
