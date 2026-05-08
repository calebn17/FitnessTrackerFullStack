"""Workout persistence."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.repository import BaseRepository
from app.domains.workouts.models import DerivedMetrics, ExerciseSet, Workout


class WorkoutRepository(BaseRepository):
    """Data access for workouts and nested rows."""

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
        )
        if exercise_sets:
            workout.exercise_sets.extend(exercise_sets)
        if derived_metrics is not None:
            workout.derived_metrics = derived_metrics
        self.session.add(workout)
        await self.session.flush()
        return workout

    async def get_by_id_for_user(
        self,
        workout_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        load_children: bool = False,
    ) -> Workout | None:
        stmt = select(Workout).where(
            Workout.id == workout_id,
            Workout.user_id == user_id,
        )
        if load_children:
            stmt = stmt.options(
                selectinload(Workout.exercise_sets),
                selectinload(Workout.derived_metrics),
                selectinload(Workout.insight),
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_workout(self, workout: Workout) -> None:
        await self.session.delete(workout)
