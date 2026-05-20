"""Workout SQLAlchemy models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.domains.ai.models import Insight
    from app.domains.users.models import User


class Workout(Base):
    """A logged workout belonging to a user."""

    __tablename__ = "workouts"
    __table_args__ = (
        Index("idx_workouts_user_id", "user_id"),
        Index("idx_workouts_date", "date"),
        Index("idx_workouts_client_id", "client_id"),
        Index("idx_workouts_user_deleted_date", "user_id", "deleted_at", "date"),
        Index("idx_workouts_user_client", "user_id", "client_id"),
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
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        unique=True,
    )
    date: Mapped[date] = mapped_column(Date(), nullable=False)
    workout_type: Mapped[str] = mapped_column(String(), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text(), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="workouts")
    exercise_sets: Mapped[list[ExerciseSet]] = relationship(
        "ExerciseSet",
        back_populates="workout",
        cascade="all, delete-orphan",
    )
    derived_metrics: Mapped[DerivedMetrics | None] = relationship(
        "DerivedMetrics",
        back_populates="workout",
        cascade="all, delete-orphan",
        uselist=False,
    )
    insight: Mapped[Insight | None] = relationship(
        "Insight",
        back_populates="workout",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ExerciseSet(Base):
    """One set within a workout."""

    __tablename__ = "exercise_sets"
    __table_args__ = (Index("idx_exercise_sets_workout_id", "workout_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    workout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    exercise_name: Mapped[str] = mapped_column(String(), nullable=False)
    set_number: Mapped[int] = mapped_column(Integer(), nullable=False)
    reps: Mapped[int] = mapped_column(Integer(), nullable=False)
    weight: Mapped[float | None] = mapped_column(Float(), nullable=True)
    weight_unit: Mapped[str] = mapped_column(String(), nullable=False, server_default=text("'lbs'"))
    rpe: Mapped[float | None] = mapped_column(Float(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    workout: Mapped[Workout] = relationship("Workout", back_populates="exercise_sets")


class DerivedMetrics(Base):
    """Aggregated metrics for a workout (one row per workout)."""

    __tablename__ = "derived_metrics"

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
    total_volume: Mapped[float | None] = mapped_column(Float(), nullable=True)
    total_sets: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    total_reps: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    avg_rpe: Mapped[float | None] = mapped_column(Float(), nullable=True)
    exercise_count: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    muscle_groups: Mapped[list[str] | None] = mapped_column(ARRAY(Text()), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    workout: Mapped[Workout] = relationship("Workout", back_populates="derived_metrics")
