"""Unit tests for workout Pydantic schemas."""

import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.domains.workouts.schemas import (
    ExerciseSetCreate,
    WorkoutCreate,
    WorkoutListParams,
)


def test_workout_create_accepts_valid_payload() -> None:
    cid = uuid.uuid4()
    body = WorkoutCreate(
        client_id=cid,
        date=date(2026, 4, 25),
        workout_type="strength",
        sets=[
            ExerciseSetCreate(
                exercise_name="Squat",
                set_number=1,
                reps=5,
                weight=225.0,
            ),
        ],
    )
    assert body.client_id == cid
    assert len(body.sets) == 1


def test_workout_create_rejects_invalid_workout_type() -> None:
    with pytest.raises(ValidationError):
        WorkoutCreate(
            client_id=uuid.uuid4(),
            date=date(2026, 4, 25),
            workout_type="invalid",
        )


def test_workout_list_params_defaults() -> None:
    p = WorkoutListParams()
    assert p.page == 1
    assert p.per_page == 20
    assert p.order_by == "date"
    assert p.order_dir == "desc"
