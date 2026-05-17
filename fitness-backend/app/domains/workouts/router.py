"""Workout HTTP routes (Phase 4+)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session, get_supabase_jwt_claims
from app.domains.workouts.schemas import (
    ExerciseSetCreate,
    ExerciseSetRead,
    ExerciseSetUpdate,
    WorkoutCreate,
    WorkoutListParams,
    WorkoutListResponse,
    WorkoutRead,
    WorkoutUpdate,
)
from app.domains.workouts.service import WorkoutService

router = APIRouter(prefix="/workouts", tags=["workouts"])


def get_workout_list_params(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    workout_type: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    order_by: Annotated[str, Query()] = "date",
    order_dir: Annotated[str, Query()] = "desc",
) -> WorkoutListParams:
    """Bind query string to a validated WorkoutListParams model."""
    try:
        return WorkoutListParams(
            page=page,
            per_page=per_page,
            workout_type=workout_type,
            date_from=date_from,
            date_to=date_to,
            order_by=order_by,
            order_dir=order_dir,
        )
    except ValidationError as exc:
        # Convert internal pydantic validation to API-friendly request validation status.
        raise RequestValidationError(exc.errors()) from exc


@router.get("", response_model=WorkoutListResponse)
async def list_workouts(
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    params: Annotated[WorkoutListParams, Depends(get_workout_list_params)],
) -> WorkoutListResponse:
    """List workouts for the authenticated user (paginated)."""
    return await WorkoutService(session).list_workouts(claims, params)


@router.post("", response_model=WorkoutRead, status_code=status.HTTP_201_CREATED)
async def create_workout(
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: WorkoutCreate,
) -> WorkoutRead:
    """Create a workout with optional nested sets."""
    return await WorkoutService(session).create_workout(claims, payload)


@router.get("/{workout_id}", response_model=WorkoutRead)
async def get_workout(
    workout_id: UUID,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> WorkoutRead:
    """Get a single workout with sets and metrics."""
    return await WorkoutService(session).get_workout(claims, workout_id)


@router.put("/{workout_id}", response_model=WorkoutRead)
async def update_workout(
    workout_id: UUID,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: WorkoutUpdate,
) -> WorkoutRead:
    """Update workout fields and optionally replace all sets."""
    return await WorkoutService(session).update_workout(claims, workout_id, payload)


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workout(
    workout_id: UUID,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """Soft-delete a workout."""
    await WorkoutService(session).soft_delete_workout(claims, workout_id)


@router.post(
    "/{workout_id}/sets",
    response_model=ExerciseSetRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_exercise_set(
    workout_id: UUID,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: ExerciseSetCreate,
) -> ExerciseSetRead:
    """Add a set to an existing workout."""
    return await WorkoutService(session).add_exercise_set(claims, workout_id, payload)


@router.put("/{workout_id}/sets/{set_id}", response_model=ExerciseSetRead)
async def update_exercise_set(
    workout_id: UUID,
    set_id: UUID,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    payload: ExerciseSetUpdate,
) -> ExerciseSetRead:
    """Update a single exercise set."""
    return await WorkoutService(session).update_exercise_set(
        claims,
        workout_id,
        set_id,
        payload,
    )


@router.delete("/{workout_id}/sets/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exercise_set(
    workout_id: UUID,
    set_id: UUID,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    """Delete a single exercise set."""
    await WorkoutService(session).delete_exercise_set(claims, workout_id, set_id)
