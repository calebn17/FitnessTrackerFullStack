"""Repository layer tests (requires Postgres + migrations)."""

import uuid
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.ai.models import Insight
from app.domains.users.repository import UserRepository
from app.domains.workouts.models import DerivedMetrics, ExerciseSet
from app.domains.workouts.repository import WorkoutRepository


@pytest.mark.asyncio
async def test_user_repository_create_and_lookup(db_session) -> None:
    users = UserRepository(db_session)
    created = await users.create(supabase_id="sub-1", email="a@example.com")
    await db_session.commit()

    by_id = await users.get_by_id(created.id)
    assert by_id is not None
    assert by_id.email == "a@example.com"

    assert (await users.get_by_email("a@example.com")) is not None
    assert (await users.get_by_supabase_id("sub-1")) is not None


@pytest.mark.asyncio
async def test_workout_repository_nested_create(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="sub-2", email="b@example.com")
    workouts = WorkoutRepository(db_session)

    exercise_set = ExerciseSet(exercise_name="Squat", set_number=1, reps=5, weight=225.0)
    metrics = DerivedMetrics(total_volume=1125.0, total_sets=1, total_reps=5)

    workout = await workouts.create_workout(
        user_id=user.id,
        workout_date=date(2026, 5, 8),
        workout_type="strength",
        notes="Leg day",
        exercise_sets=[exercise_set],
        derived_metrics=metrics,
    )
    await db_session.commit()

    loaded = await workouts.get_by_id_for_user(workout.id, user.id, load_children=True)
    assert loaded is not None
    assert len(loaded.exercise_sets) == 1
    assert loaded.derived_metrics is not None
    assert loaded.derived_metrics.total_volume == 1125.0


@pytest.mark.asyncio
async def test_workout_client_id_unique(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="sub-3", email="c@example.com")
    workouts = WorkoutRepository(db_session)
    client_id = uuid.uuid4()

    await workouts.create_workout(
        user_id=user.id,
        workout_date=date(2026, 5, 8),
        workout_type="strength",
        client_id=client_id,
    )
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await workouts.create_workout(
            user_id=user.id,
            workout_date=date(2026, 5, 9),
            workout_type="strength",
            client_id=client_id,
        )
    await db_session.rollback()


@pytest.mark.asyncio
async def test_delete_workout_cascades_children(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="sub-4", email="d@example.com")
    workouts = WorkoutRepository(db_session)

    workout = await workouts.create_workout(
        user_id=user.id,
        workout_date=date(2026, 5, 8),
        workout_type="strength",
        exercise_sets=[ExerciseSet(exercise_name="Pull-up", set_number=1, reps=10)],
        derived_metrics=DerivedMetrics(total_sets=1),
    )
    workout.insight = Insight(ai_output={"summary": "ok"})
    await db_session.commit()

    await workouts.delete_workout(workout)
    await db_session.commit()

    assert await workouts.get_by_id_for_user(workout.id, user.id) is None
