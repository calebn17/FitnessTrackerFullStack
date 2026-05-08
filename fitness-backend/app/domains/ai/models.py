"""Insight SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.domains.workouts.models import Workout


class Insight(Base):
    """Stored AI evaluation output for a workout."""

    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    workout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workouts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    ai_output: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(), nullable=True)
    evaluation_score: Mapped[float | None] = mapped_column(Float(), nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    status: Mapped[str] = mapped_column(String(), nullable=False, server_default=text("'pending'"))
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    workout: Mapped[Workout] = relationship("Workout", back_populates="insight")
