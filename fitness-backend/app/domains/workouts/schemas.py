"""Pydantic schemas for workouts and exercise sets (Phase 4+)."""

import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_WORKOUT_TYPE_PATTERN = r"^(strength|cardio|flexibility|other)$"
_WEIGHT_UNIT_PATTERN = r"^(lbs|kg)$"
_ORDER_BY_PATTERN = r"^(date|created_at)$"
_ORDER_DIR_PATTERN = r"^(asc|desc)$"


class ExerciseSetCreate(BaseModel):
    """Payload to create one exercise set."""

    exercise_name: str = Field(..., min_length=1, max_length=100)
    set_number: int = Field(..., ge=1)
    reps: int = Field(..., ge=1, le=1000)
    weight: float | None = Field(None, ge=0)
    weight_unit: str = Field("lbs", pattern=_WEIGHT_UNIT_PATTERN)
    rpe: float | None = Field(None, ge=1, le=10)


class ExerciseSetUpdate(BaseModel):
    """Partial update for an exercise set."""

    exercise_name: str | None = Field(None, min_length=1, max_length=100)
    set_number: int | None = Field(None, ge=1)
    reps: int | None = Field(None, ge=1, le=1000)
    weight: float | None = Field(None, ge=0)
    weight_unit: str | None = Field(None, pattern=_WEIGHT_UNIT_PATTERN)
    rpe: float | None = Field(None, ge=1, le=10)


class ExerciseSetRead(BaseModel):
    """Serialized exercise set."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    exercise_name: str
    set_number: int
    reps: int
    weight: float | None
    weight_unit: str
    rpe: float | None
    created_at: datetime.datetime


class DerivedMetricsRead(BaseModel):
    """Serialized derived metrics row (optional on workout)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    total_volume: float | None
    total_sets: int | None
    total_reps: int | None
    avg_rpe: float | None
    exercise_count: int | None
    muscle_groups: list[str] | None
    created_at: datetime.datetime


class WorkoutCreate(BaseModel):
    """Create workout with optional nested sets."""

    client_id: UUID
    date: datetime.date
    workout_type: str = Field(..., pattern=_WORKOUT_TYPE_PATTERN)
    notes: str | None = Field(None, max_length=1000)
    sets: list[ExerciseSetCreate] = Field(default_factory=list)


class WorkoutUpdate(BaseModel):
    """Update workout metadata and optionally replace sets."""

    date: datetime.date | None = None
    workout_type: str | None = Field(None, pattern=_WORKOUT_TYPE_PATTERN)
    notes: str | None = Field(None, max_length=1000)
    sets: list[ExerciseSetCreate] | None = None


class WorkoutRead(BaseModel):
    """Serialized workout with nested sets and optional metrics / insight."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    client_id: UUID | None
    date: datetime.date
    workout_type: str
    notes: str | None
    sets: list[ExerciseSetRead]
    metrics: DerivedMetricsRead | None
    insight_status: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime | None


class WorkoutListParams(BaseModel):
    """Query parameters for listing workouts."""

    page: int = Field(1, ge=1)
    per_page: int = Field(20, ge=1, le=100)
    workout_type: str | None = Field(None, pattern=_WORKOUT_TYPE_PATTERN)
    date_from: datetime.date | None = None
    date_to: datetime.date | None = None
    order_by: str = Field("date", pattern=_ORDER_BY_PATTERN)
    order_dir: str = Field("desc", pattern=_ORDER_DIR_PATTERN)


class WorkoutListResponse(BaseModel):
    """Paginated list of workouts."""

    items: list[WorkoutRead]
    total: int
    page: int
    per_page: int
