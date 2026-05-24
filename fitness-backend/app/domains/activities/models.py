"""SQLAlchemy models for Strava activities and OAuth tokens."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

PROVIDER_STRAVA = "strava"
PROVIDER_WHOOP = "whoop"


class OAuthToken(Base):
    """OAuth credentials for an external fitness provider."""

    __tablename__ = "oauth_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_oauth_tokens_user_provider"),
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
    provider: Mapped[str] = mapped_column(String(), nullable=False)
    access_token: Mapped[str] = mapped_column(Text(), nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    athlete_id: Mapped[str | None] = mapped_column(String(), nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StravaActivity(Base):
    """Synced running activity from Strava."""

    __tablename__ = "strava_activities"

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
    strava_id: Mapped[int] = mapped_column(BigInteger(), nullable=False, unique=True)
    sport_type: Mapped[str] = mapped_column(String(), nullable=False)
    start_date_local: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    distance: Mapped[float] = mapped_column(Float(), nullable=False)
    moving_time: Mapped[int] = mapped_column(Integer(), nullable=False)
    elapsed_time: Mapped[int] = mapped_column(Integer(), nullable=False)
    average_speed: Mapped[float] = mapped_column(Float(), nullable=False)
    max_speed: Mapped[float | None] = mapped_column(Float(), nullable=True)
    total_elevation_gain: Mapped[float] = mapped_column(Float(), nullable=False)
    average_heartrate: Mapped[float | None] = mapped_column(Float(), nullable=True)
    max_heartrate: Mapped[float | None] = mapped_column(Float(), nullable=True)
    average_cadence: Mapped[float | None] = mapped_column(Float(), nullable=True)
    calories: Mapped[float | None] = mapped_column(Float(), nullable=True)
    pr_count: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
