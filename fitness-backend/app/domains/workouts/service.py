"""Workout business logic (Phase 4+)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.users.service import UserService
from app.domains.workouts.models import ExerciseSet, Workout
from app.domains.workouts.repository import WorkoutRepository
from app.domains.workouts.schemas import (
    DerivedMetricsRead,
    ExerciseSetCreate,
    ExerciseSetRead,
    ExerciseSetUpdate,
    WorkoutCreate,
    WorkoutListParams,
    WorkoutListResponse,
    WorkoutRead,
    WorkoutUpdate,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _exercise_set_from_create(
    data: ExerciseSetCreate,
    *,
    workout_id: uuid.UUID | None = None,
) -> ExerciseSet:
    if workout_id is None:
        return ExerciseSet(
            exercise_name=data.exercise_name,
            set_number=data.set_number,
            reps=data.reps,
            weight=data.weight,
            weight_unit=data.weight_unit,
            rpe=data.rpe,
        )
    return ExerciseSet(
        workout_id=workout_id,
        exercise_name=data.exercise_name,
        set_number=data.set_number,
        reps=data.reps,
        weight=data.weight,
        weight_unit=data.weight_unit,
        rpe=data.rpe,
    )


def serialize_workout_read(workout: Workout) -> WorkoutRead:
    """Map ORM workout (with children loaded) to API read model."""
    sets_sorted = sorted(
        workout.exercise_sets,
        key=lambda s: (s.set_number, s.created_at),
    )
    sets = [ExerciseSetRead.model_validate(s) for s in sets_sorted]
    metrics = (
        DerivedMetricsRead.model_validate(workout.derived_metrics)
        if workout.derived_metrics is not None
        else None
    )
    insight_status = workout.insight.status if workout.insight is not None else None
    return WorkoutRead(
        id=workout.id,
        client_id=workout.client_id,
        date=workout.date,
        workout_type=workout.workout_type,
        notes=workout.notes,
        sets=sets,
        metrics=metrics,
        insight_status=insight_status,
        created_at=workout.created_at,
        updated_at=workout.updated_at,
    )


class WorkoutService:
    """Coordinates workout persistence for authenticated users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._workouts = WorkoutRepository(session)

    async def _ensure_metrics_for_workout(self, workout: Workout) -> None:
        if workout.derived_metrics is None:
            await self._workouts.refresh_derived_metrics(workout)
            await self._session.commit()
            await self._session.refresh(
                workout,
                attribute_names=["exercise_sets", "derived_metrics", "insight"],
            )

    async def _user_from_claims(self, claims: dict[str, Any]) -> uuid.UUID:
        try:
            user = await UserService(self._session).get_or_create_from_supabase(claims)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "invalid_user_claims", "errors": exc.errors()},
            ) from exc
        return user.id

    async def create_workout(
        self,
        claims: dict[str, Any],
        payload: WorkoutCreate,
    ) -> WorkoutRead:
        user_id = await self._user_from_claims(claims)
        exercise_sets = [_exercise_set_from_create(s) for s in payload.sets]
        try:
            workout = await self._workouts.create_workout(
                user_id=user_id,
                workout_date=payload.date,
                workout_type=payload.workout_type,
                notes=payload.notes,
                client_id=payload.client_id,
                exercise_sets=exercise_sets,
            )
            await self._workouts.refresh_derived_metrics(workout)
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "duplicate_client_id",
                    "message": "A workout with this client_id already exists.",
                },
            ) from exc

        loaded = await self._workouts.get_by_id_for_user(
            workout.id,
            user_id,
            load_children=True,
        )
        assert loaded is not None
        return serialize_workout_read(loaded)

    async def list_workouts(
        self,
        claims: dict[str, Any],
        params: WorkoutListParams,
    ) -> WorkoutListResponse:
        user_id = await self._user_from_claims(claims)
        total = await self._workouts.count_for_user(user_id, params)
        rows = await self._workouts.list_for_user(
            user_id,
            params,
            load_children=True,
        )
        for row in rows:
            await self._ensure_metrics_for_workout(row)
        items = [serialize_workout_read(w) for w in rows]
        return WorkoutListResponse(
            items=items,
            total=total,
            page=params.page,
            per_page=params.per_page,
        )

    async def get_workout(
        self,
        claims: dict[str, Any],
        workout_id: uuid.UUID,
    ) -> WorkoutRead:
        user_id = await self._user_from_claims(claims)
        workout = await self._workouts.get_by_id_for_user(
            workout_id,
            user_id,
            load_children=True,
        )
        if workout is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "workout_not_found", "message": "Workout not found."},
            )
        await self._ensure_metrics_for_workout(workout)
        return serialize_workout_read(workout)

    async def update_workout(
        self,
        claims: dict[str, Any],
        workout_id: uuid.UUID,
        payload: WorkoutUpdate,
    ) -> WorkoutRead:
        user_id = await self._user_from_claims(claims)
        workout = await self._workouts.get_by_id_for_user(
            workout_id,
            user_id,
            load_children=True,
        )
        if workout is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "workout_not_found", "message": "Workout not found."},
            )
        now = _utcnow()
        if payload.date is not None:
            workout.date = payload.date
        if payload.workout_type is not None:
            workout.workout_type = payload.workout_type
        if "notes" in payload.model_fields_set:
            workout.notes = payload.notes
        if payload.sets is not None:
            new_sets = [_exercise_set_from_create(s) for s in payload.sets]
            await self._workouts.replace_exercise_sets(workout, new_sets)
            await self._workouts.refresh_derived_metrics(workout)
        elif workout.derived_metrics is None:
            await self._workouts.refresh_derived_metrics(workout)
        workout.updated_at = now
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "duplicate_client_id",
                    "message": "Conflict while saving workout.",
                },
            ) from exc

        loaded = await self._workouts.get_by_id_for_user(
            workout_id,
            user_id,
            load_children=True,
        )
        assert loaded is not None
        return serialize_workout_read(loaded)

    async def soft_delete_workout(
        self,
        claims: dict[str, Any],
        workout_id: uuid.UUID,
    ) -> None:
        user_id = await self._user_from_claims(claims)
        workout = await self._workouts.get_by_id_for_user(
            workout_id,
            user_id,
            load_children=False,
        )
        if workout is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "workout_not_found", "message": "Workout not found."},
            )
        await self._workouts.soft_delete_workout(workout, when=_utcnow())
        await self._session.commit()

    async def add_exercise_set(
        self,
        claims: dict[str, Any],
        workout_id: uuid.UUID,
        payload: ExerciseSetCreate,
    ) -> ExerciseSetRead:
        user_id = await self._user_from_claims(claims)
        workout = await self._workouts.get_by_id_for_user(workout_id, user_id)
        if workout is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "workout_not_found", "message": "Workout not found."},
            )
        new_set = _exercise_set_from_create(payload, workout_id=workout.id)
        self._session.add(new_set)
        await self._session.flush()
        workout_for_metrics = await self._workouts.get_by_id_for_user(
            workout_id,
            user_id,
            load_children=True,
        )
        if workout_for_metrics is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "workout_not_found", "message": "Workout not found."},
            )
        await self._workouts.refresh_derived_metrics(workout_for_metrics)
        await self._workouts.touch_workout_updated(workout_for_metrics, when=_utcnow())
        await self._session.commit()
        await self._session.refresh(new_set)
        return ExerciseSetRead.model_validate(new_set)

    async def update_exercise_set(
        self,
        claims: dict[str, Any],
        workout_id: uuid.UUID,
        set_id: uuid.UUID,
        payload: ExerciseSetUpdate,
    ) -> ExerciseSetRead:
        user_id = await self._user_from_claims(claims)
        es = await self._workouts.get_exercise_set_for_user(workout_id, set_id, user_id)
        if es is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "set_not_found", "message": "Exercise set not found."},
            )
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            setattr(es, key, value)
        await self._session.flush()
        workout = await self._workouts.get_by_id_for_user(
            workout_id,
            user_id,
            load_children=True,
        )
        if workout is not None:
            await self._workouts.refresh_derived_metrics(workout)
            await self._workouts.touch_workout_updated(workout, when=_utcnow())
        await self._session.commit()
        await self._session.refresh(es)
        return ExerciseSetRead.model_validate(es)

    async def delete_exercise_set(
        self,
        claims: dict[str, Any],
        workout_id: uuid.UUID,
        set_id: uuid.UUID,
    ) -> None:
        user_id = await self._user_from_claims(claims)
        es = await self._workouts.get_exercise_set_for_user(workout_id, set_id, user_id)
        if es is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "set_not_found", "message": "Exercise set not found."},
            )
        await self._session.delete(es)
        await self._session.flush()
        workout = await self._workouts.get_by_id_for_user(
            workout_id,
            user_id,
            load_children=True,
        )
        if workout is not None:
            await self._workouts.refresh_derived_metrics(workout)
            await self._workouts.touch_workout_updated(workout, when=_utcnow())
        await self._session.commit()
