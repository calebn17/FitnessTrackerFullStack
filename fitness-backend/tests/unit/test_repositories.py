"""Repository layer tests (requires Postgres + migrations)."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.activities.models import PROVIDER_STRAVA
from app.domains.activities.repository import OAuthTokenRepository, StravaActivityRepository
from app.domains.ai.models import Insight
from app.domains.health.repository import DailyHealthRepository
from app.domains.users.repository import UserRepository
from app.domains.workouts.models import DerivedMetrics, ExerciseSet
from app.domains.workouts.repository import WorkoutRepository
from app.domains.workouts.schemas import WorkoutListParams


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


@pytest.mark.asyncio
async def test_workout_repository_list_count_and_soft_delete(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="sub-list", email="list@example.com")
    workouts = WorkoutRepository(db_session)
    now = datetime.now(UTC)

    for day in (8, 9, 10):
        await workouts.create_workout(
            user_id=user.id,
            workout_date=date(2026, 5, day),
            workout_type="strength",
        )
    await db_session.commit()

    total = await workouts.count_for_user(user.id, WorkoutListParams(page=1, per_page=20))
    assert total == 3

    page1 = await workouts.list_for_user(
        user.id,
        WorkoutListParams(page=1, per_page=2, order_by="date", order_dir="desc"),
    )
    assert len(page1) == 2
    assert page1[0].date == date(2026, 5, 10)

    to_hide = page1[0]
    await workouts.soft_delete_workout(to_hide, when=now)
    await db_session.commit()

    assert await workouts.get_by_id_for_user(to_hide.id, user.id) is None
    after = await workouts.count_for_user(user.id, WorkoutListParams())
    assert after == 2


@pytest.mark.asyncio
async def test_workout_repository_get_by_client_id(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="sub-cid", email="cid@example.com")
    workouts = WorkoutRepository(db_session)
    cid = uuid.uuid4()
    await workouts.create_workout(
        user_id=user.id,
        workout_date=date(2026, 5, 1),
        workout_type="strength",
        client_id=cid,
        exercise_sets=[ExerciseSet(exercise_name="Squat", set_number=1, reps=5, weight=100.0)],
    )
    await db_session.commit()

    found = await workouts.get_by_client_id_for_user(cid, user.id, load_children=True)
    assert found is not None
    assert found.client_id == cid
    assert len(found.exercise_sets) == 1

    assert await workouts.get_by_client_id_for_user(uuid.uuid4(), user.id) is None


@pytest.mark.asyncio
async def test_workout_repository_list_changed_since(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="sub-since", email="since@example.com")
    workouts = WorkoutRepository(db_session)
    t0 = datetime.now(UTC)
    w = await workouts.create_workout(
        user_id=user.id,
        workout_date=date(2026, 5, 1),
        workout_type="strength",
    )
    await db_session.commit()

    changed_early = await workouts.list_changed_since_for_user(user.id, t0)
    assert any(row.id == w.id for row in changed_early)

    since_future = datetime(2099, 1, 1, tzinfo=UTC)
    assert not await workouts.list_changed_since_for_user(user.id, since_future)

    since_before_update = datetime.now(UTC)
    await workouts.touch_workout_updated(w, when=datetime.now(UTC))
    await db_session.commit()

    after_touch = await workouts.list_changed_since_for_user(user.id, since_before_update)
    assert any(row.id == w.id for row in after_touch)

    since_before_delete = datetime.now(UTC)
    await workouts.soft_delete_workout(w, when=datetime.now(UTC))
    await db_session.commit()

    after_delete = await workouts.list_changed_since_for_user(user.id, since_before_delete)
    assert any(row.id == w.id and row.deleted_at is not None for row in after_delete)


@pytest.mark.asyncio
async def test_workout_repository_refresh_derived_metrics_upserts_one_row(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="sub-metrics", email="metrics@example.com")
    workouts = WorkoutRepository(db_session)
    es = ExerciseSet(exercise_name="Squat", set_number=1, reps=5, weight=200.0)
    workout = await workouts.create_workout(
        user_id=user.id,
        workout_date=date(2026, 5, 1),
        workout_type="strength",
        exercise_sets=[es],
    )
    await db_session.commit()

    loaded = await workouts.get_by_id_for_user(workout.id, user.id, load_children=True)
    assert loaded is not None
    m1 = await workouts.refresh_derived_metrics(loaded)
    first_id = m1.id
    await db_session.commit()

    loaded2 = await workouts.get_by_id_for_user(workout.id, user.id, load_children=True)
    assert loaded2 is not None
    # Add a set in memory like service would after reload
    loaded2.exercise_sets.append(
        ExerciseSet(
            exercise_name="Squat",
            set_number=2,
            reps=3,
            weight=250.0,
        ),
    )
    m2 = await workouts.refresh_derived_metrics(loaded2)
    assert m2.id == first_id
    assert m2.total_sets == 2
    assert m2.total_reps == 8
    assert m2.total_volume == 5 * 200.0 + 3 * 250.0
    await db_session.commit()

    loaded3 = await workouts.get_by_id_for_user(workout.id, user.id, load_children=True)
    assert loaded3 is not None
    assert loaded3.derived_metrics is not None
    assert loaded3.derived_metrics.id == first_id


@pytest.mark.asyncio
async def test_workout_repository_refresh_derived_metrics_loads_unloaded_relationships(
    db_session,
) -> None:
    users = UserRepository(db_session)
    user = await users.create(
        supabase_id="sub-metrics-unloaded",
        email="metrics-unloaded@example.com",
    )
    workouts = WorkoutRepository(db_session)
    workout = await workouts.create_workout(
        user_id=user.id,
        workout_date=date(2026, 5, 2),
        workout_type="strength",
        exercise_sets=[ExerciseSet(exercise_name="Deadlift", set_number=1, reps=5, weight=300.0)],
    )
    await workouts.refresh_derived_metrics(workout)
    await db_session.commit()
    db_session.expunge_all()

    shallow = await workouts.get_by_id_for_user(workout.id, user.id, load_children=False)
    assert shallow is not None
    assert "exercise_sets" not in shallow.__dict__
    assert "derived_metrics" not in shallow.__dict__

    refreshed = await workouts.refresh_derived_metrics(shallow)
    assert refreshed.total_sets == 1
    assert refreshed.total_reps == 5
    assert refreshed.total_volume == 5 * 300.0


@pytest.mark.asyncio
async def test_workout_repository_get_exercise_set_for_user(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="sub-set", email="set@example.com")
    workouts = WorkoutRepository(db_session)
    es = ExerciseSet(exercise_name="Bench", set_number=1, reps=8, weight=135.0)
    workout = await workouts.create_workout(
        user_id=user.id,
        workout_date=date(2026, 5, 1),
        workout_type="strength",
        exercise_sets=[es],
    )
    await db_session.commit()
    sid = workout.exercise_sets[0].id

    found = await workouts.get_exercise_set_for_user(workout.id, sid, user.id)
    assert found is not None
    assert found.exercise_name == "Bench"

    other = await users.create(supabase_id="sub-other", email="other@example.com")
    assert await workouts.get_exercise_set_for_user(workout.id, sid, other.id) is None


@pytest.mark.asyncio
async def test_oauth_token_repository_upsert(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="oauth-repo-sub", email="oauth-repo@example.com")
    tokens = OAuthTokenRepository(db_session)
    first = await tokens.upsert(
        user_id=user.id,
        provider=PROVIDER_STRAVA,
        access_token="a1",
        refresh_token="r1",
        expires_at=datetime.now(UTC),
    )
    second = await tokens.upsert(
        user_id=user.id,
        provider=PROVIDER_STRAVA,
        access_token="a2",
        refresh_token="r2",
        expires_at=datetime.now(UTC),
    )
    await db_session.commit()
    assert first.id == second.id
    loaded = await tokens.get_for_user_provider(user.id, PROVIDER_STRAVA)
    assert loaded is not None
    assert loaded.access_token == "a2"


@pytest.mark.asyncio
async def test_strava_activity_repository_upsert_and_list(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="strava-repo-sub", email="strava-repo@example.com")
    activities = StravaActivityRepository(db_session)
    await activities.upsert_activity(
        user_id=user.id,
        values={
            "strava_id": 4242,
            "sport_type": "Run",
            "start_date_local": datetime.now(UTC),
            "distance": 1000.0,
            "moving_time": 600,
            "elapsed_time": 620,
            "average_speed": 1.6,
            "total_elevation_gain": 10.0,
            "pr_count": 0,
        },
    )
    await db_session.commit()
    rows = await activities.list_recent(user.id, limit=5)
    assert len(rows) == 1
    assert rows[0].strava_id == 4242


@pytest.mark.asyncio
async def test_daily_health_repository_upsert(db_session) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="health-repo-sub", email="health-repo@example.com")
    health = DailyHealthRepository(db_session)
    await health.upsert_record(
        user_id=user.id,
        values={
            "date": date(2026, 5, 20),
            "provider": "whoop",
            "sleep_score": 80,
            "recovery_score": 70,
        },
    )
    await db_session.commit()
    row = await health.get_for_date(user.id, date(2026, 5, 20), provider="whoop")
    assert row is not None
    assert row.sleep_score == 80
