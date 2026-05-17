"""Workout persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.domains.workouts.metrics import (
    apply_values_to_derived_metrics,
    calculate_derived_metrics_values,
)
from app.domains.workouts.models import DerivedMetrics, ExerciseSet, Workout
from app.domains.workouts.schemas import WorkoutListParams

_UNLOADED_DERIVED_METRICS: object = object()
_UNLOADED_EXERCISE_SETS: object = object()


class WorkoutRepository(BaseRepository):
    """Data access for workouts and nested rows."""

    def _not_deleted(self) -> Any:
        return Workout.deleted_at.is_(None)

    def _apply_list_filters(
        self,
        stmt: Select[Any],
        *,
        user_id: uuid.UUID,
        params: WorkoutListParams,
    ) -> Select[Any]:
        stmt = stmt.where(Workout.user_id == user_id, self._not_deleted())
        if params.workout_type is not None:
            stmt = stmt.where(Workout.workout_type == params.workout_type)
        if params.date_from is not None:
            stmt = stmt.where(Workout.date >= params.date_from)
        if params.date_to is not None:
            stmt = stmt.where(Workout.date <= params.date_to)
        return stmt

    async def create_workout(
        self,
        *,
        user_id: uuid.UUID,
        workout_date: date,
        workout_type: str,
        notes: str | None = None,
        client_id: uuid.UUID | None = None,
        exercise_sets: list[ExerciseSet] | None = None,
        derived_metrics: DerivedMetrics | None = None,
    ) -> Workout:
        workout = Workout(
            user_id=user_id,
            date=workout_date,
            workout_type=workout_type,
            notes=notes,
            client_id=client_id,
            # Keep write-side timestamps on the same clock as sync/list `since` values.
            created_at=datetime.now(UTC),
        )
        if exercise_sets is not None:
            workout.exercise_sets.extend(exercise_sets)
        if derived_metrics is not None:
            workout.derived_metrics = derived_metrics
        self.session.add(workout)
        await self.session.flush()
        return workout

    async def refresh_derived_metrics(self, workout: Workout) -> DerivedMetrics:
        """Recompute and upsert the one-to-one derived_metrics row for this workout."""
        raw_sets = workout.__dict__.get("exercise_sets", _UNLOADED_EXERCISE_SETS)
        raw_dm = workout.__dict__.get("derived_metrics", _UNLOADED_DERIVED_METRICS)
        if raw_sets is _UNLOADED_EXERCISE_SETS or raw_dm is _UNLOADED_DERIVED_METRICS:
            await self.session.refresh(
                workout,
                attribute_names=["exercise_sets", "derived_metrics"],
            )
            raw_sets = workout.__dict__.get("exercise_sets", _UNLOADED_EXERCISE_SETS)
            raw_dm = workout.__dict__.get("derived_metrics", _UNLOADED_DERIVED_METRICS)
        sets_for_calc: list[ExerciseSet] = (
            [] if raw_sets is _UNLOADED_EXERCISE_SETS else list(raw_sets)
        )
        values = calculate_derived_metrics_values(sets_for_calc)
        if raw_dm is _UNLOADED_DERIVED_METRICS or raw_dm is None:
            metrics_row = DerivedMetrics()
            workout.derived_metrics = metrics_row
        else:
            metrics_row = raw_dm
        apply_values_to_derived_metrics(metrics_row, values)
        await self.session.flush()
        return metrics_row

    async def get_by_id_for_user(
        self,
        workout_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        load_children: bool = False,
        include_deleted: bool = False,
    ) -> Workout | None:
        stmt = select(Workout).where(
            Workout.id == workout_id,
            Workout.user_id == user_id,
        )
        if not include_deleted:
            stmt = stmt.where(self._not_deleted())
        if load_children:
            stmt = stmt.options(
                selectinload(Workout.exercise_sets),
                selectinload(Workout.derived_metrics),
                selectinload(Workout.insight),
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_for_user(self, user_id: uuid.UUID, params: WorkoutListParams) -> int:
        stmt = select(func.count()).select_from(Workout)
        stmt = self._apply_list_filters(stmt, user_id=user_id, params=params)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        params: WorkoutListParams,
        *,
        load_children: bool = False,
    ) -> list[Workout]:
        stmt = select(Workout)
        stmt = self._apply_list_filters(stmt, user_id=user_id, params=params)
        order_col = Workout.date if params.order_by == "date" else Workout.created_at
        stmt = stmt.order_by(
            order_col.asc() if params.order_dir == "asc" else order_col.desc(),
        )
        offset = (params.page - 1) * params.per_page
        stmt = stmt.offset(offset).limit(params.per_page)
        if load_children:
            stmt = stmt.options(
                selectinload(Workout.exercise_sets),
                selectinload(Workout.derived_metrics),
                selectinload(Workout.insight),
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_by_client_id_for_user(
        self,
        client_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        load_children: bool = False,
        include_deleted: bool = False,
    ) -> Workout | None:
        """Lookup a workout by stable client_id (offline dedupe key)."""
        stmt = select(Workout).where(
            Workout.client_id == client_id,
            Workout.user_id == user_id,
        )
        if not include_deleted:
            stmt = stmt.where(self._not_deleted())
        if load_children:
            stmt = stmt.options(
                selectinload(Workout.exercise_sets),
                selectinload(Workout.derived_metrics),
                selectinload(Workout.insight),
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_changed_since_for_user(
        self,
        user_id: uuid.UUID,
        since: datetime,
        *,
        load_children: bool = True,
    ) -> list[Workout]:
        """Rows touched after ``since`` (create, update, or soft-delete timestamp)."""
        stmt = (
            select(Workout)
            .where(
                Workout.user_id == user_id,
                or_(
                    Workout.created_at > since,
                    and_(Workout.updated_at.isnot(None), Workout.updated_at > since),
                    and_(Workout.deleted_at.isnot(None), Workout.deleted_at > since),
                ),
            )
            .order_by(Workout.created_at.asc())
        )
        if load_children:
            stmt = stmt.options(
                selectinload(Workout.exercise_sets),
                selectinload(Workout.derived_metrics),
                selectinload(Workout.insight),
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().unique().all())

    async def soft_delete_workout(self, workout: Workout, *, when: datetime) -> None:
        workout.deleted_at = when
        workout.updated_at = when
        await self.session.flush()

    async def touch_workout_updated(self, workout: Workout, *, when: datetime) -> None:
        workout.updated_at = when
        await self.session.flush()

    async def replace_exercise_sets(self, workout: Workout, sets: list[ExerciseSet]) -> None:
        workout.exercise_sets.clear()
        workout.exercise_sets.extend(sets)
        await self.session.flush()

    async def get_exercise_set_for_user(
        self,
        workout_id: uuid.UUID,
        set_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ExerciseSet | None:
        stmt = (
            select(ExerciseSet)
            .join(Workout, ExerciseSet.workout_id == Workout.id)
            .where(
                ExerciseSet.id == set_id,
                ExerciseSet.workout_id == workout_id,
                Workout.user_id == user_id,
                self._not_deleted(),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_workout(self, workout: Workout) -> None:
        await self.session.delete(workout)
