"""Integration tests for /api/v1/workouts routes (Postgres + migrations)."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import date

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.core.database import get_session_factory
from app.dependencies import get_db_session
from app.domains.ai import models as _ai_models  # noqa: F401
from app.domains.users.models import User
from app.domains.workouts import models as _workout_models  # noqa: F401
from app.domains.workouts.models import DerivedMetrics, Workout
from app.main import create_app

_SECRET = "integration-test-jwt-secret-32bytes-min"
_AUDIENCE = "authenticated"


def _database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://fitness:fitness@127.0.0.1:5433/fitness",
    )


def _encode_claims(**payload_overrides: object) -> str:
    now = int(time.time())
    payload: dict[str, object] = {
        "sub": "33333333-3333-3333-3333-333333333333",
        "email": "workout-user@example.com",
        "aud": _AUDIENCE,
        "exp": now + 3600,
    }
    payload.update(payload_overrides)
    return jwt.encode(payload, _SECRET, algorithm="HS256")


@pytest.fixture
async def client(
    db_session: AsyncSession,
) -> AsyncGenerator[TestClient, None]:
    assert db_session is not None

    def override_settings() -> Settings:
        return Settings(
            database_url=_database_url(),
            supabase_jwt_secret=_SECRET,
            supabase_jwt_audience=_AUDIENCE,
        )

    async def override_db_session() -> AsyncGenerator[AsyncSession, None]:
        engine = create_async_engine(_database_url())
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as session:
            yield session
        await engine.dispose()

    app = create_app()
    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_workouts_list_unauthorized(client: TestClient) -> None:
    r = client.get("/api/v1/workouts")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "missing_authorization"


@pytest.mark.asyncio
async def test_workouts_crud_and_sets(client: TestClient) -> None:
    sub = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    token = _encode_claims(sub=sub, email="crud@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    cid = str(uuid.uuid4())

    create_body = {
        "client_id": cid,
        "date": "2026-04-25",
        "workout_type": "strength",
        "sets": [
            {
                "exercise_name": "Squat",
                "set_number": 1,
                "reps": 5,
                "weight": 225,
            },
        ],
    }
    c = client.post("/api/v1/workouts", json=create_body, headers=headers)
    assert c.status_code == 201, c.text
    wid = c.json()["id"]
    assert c.json()["client_id"] == cid
    assert len(c.json()["sets"]) == 1
    m0 = c.json()["metrics"]
    assert m0 is not None
    assert m0["total_volume"] == 5 * 225
    assert m0["total_sets"] == 1
    assert m0["total_reps"] == 5
    assert m0["avg_rpe"] is None
    assert m0["exercise_count"] == 1
    assert set(m0["muscle_groups"] or []) == {"quadriceps", "glutes", "hamstrings"}

    g = client.get(f"/api/v1/workouts/{wid}", headers=headers)
    assert g.status_code == 200
    assert g.json()["id"] == wid
    assert g.json()["metrics"]["total_volume"] == 5 * 225

    add = client.post(
        f"/api/v1/workouts/{wid}/sets",
        json={
            "exercise_name": "Squat",
            "set_number": 2,
            "reps": 3,
            "weight": 315,
        },
        headers=headers,
    )
    assert add.status_code == 201, add.text
    sid = add.json()["id"]
    g2 = client.get(f"/api/v1/workouts/{wid}", headers=headers)
    assert g2.json()["metrics"]["total_sets"] == 2
    assert g2.json()["metrics"]["total_reps"] == 8
    assert g2.json()["metrics"]["total_volume"] == 5 * 225 + 3 * 315

    up = client.put(
        f"/api/v1/workouts/{wid}/sets/{sid}",
        json={"reps": 2},
        headers=headers,
    )
    assert up.status_code == 200
    assert up.json()["reps"] == 2
    g3 = client.get(f"/api/v1/workouts/{wid}", headers=headers)
    assert g3.json()["metrics"]["total_volume"] == 5 * 225 + 2 * 315
    assert g3.json()["metrics"]["total_reps"] == 7

    dl = client.delete(f"/api/v1/workouts/{wid}/sets/{sid}", headers=headers)
    assert dl.status_code == 204
    g4 = client.get(f"/api/v1/workouts/{wid}", headers=headers)
    assert g4.json()["metrics"]["total_sets"] == 1
    assert g4.json()["metrics"]["total_volume"] == 5 * 225

    upd = client.put(
        f"/api/v1/workouts/{wid}",
        json={"notes": "updated"},
        headers=headers,
    )
    assert upd.status_code == 200
    assert upd.json()["notes"] == "updated"
    assert upd.json()["metrics"]["total_volume"] == 5 * 225

    d = client.delete(f"/api/v1/workouts/{wid}", headers=headers)
    assert d.status_code == 204

    gone = client.get(f"/api/v1/workouts/{wid}", headers=headers)
    assert gone.status_code == 404
    assert gone.json()["detail"]["code"] == "workout_not_found"


@pytest.mark.asyncio
async def test_workouts_metrics_in_list_and_empty_sets(client: TestClient) -> None:
    sub = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    token = _encode_claims(sub=sub, email="metrics-list@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    empty = client.post(
        "/api/v1/workouts",
        json={
            "client_id": str(uuid.uuid4()),
            "date": "2026-09-01",
            "workout_type": "strength",
            "sets": [],
        },
        headers=headers,
    )
    assert empty.status_code == 201, empty.text
    eid = empty.json()["id"]
    em = empty.json()["metrics"]
    assert em is not None
    assert em["total_volume"] == 0
    assert em["total_sets"] == 0
    assert em["total_reps"] == 0
    assert em["avg_rpe"] is None
    assert em["exercise_count"] == 0
    assert em["muscle_groups"] == []

    lst = client.get("/api/v1/workouts?page=1&per_page=50", headers=headers)
    assert lst.status_code == 200
    found = next(i for i in lst.json()["items"] if i["id"] == eid)
    assert found["metrics"]["total_sets"] == 0

    unk = client.post(
        "/api/v1/workouts",
        json={
            "client_id": str(uuid.uuid4()),
            "date": "2026-09-02",
            "workout_type": "strength",
            "sets": [
                {
                    "exercise_name": "Mystery Move",
                    "set_number": 1,
                    "reps": 10,
                    "weight": 25,
                    "rpe": 7,
                },
            ],
        },
        headers=headers,
    )
    assert unk.status_code == 201, unk.text
    um = unk.json()["metrics"]
    assert um["total_volume"] == 250.0
    assert um["muscle_groups"] == []
    assert um["avg_rpe"] == 7.0


@pytest.mark.asyncio
async def test_workouts_read_paths_backfill_metrics_for_legacy_rows(client: TestClient) -> None:
    sub = "acacacac-acac-acac-acac-acacacacacac"
    token = _encode_claims(sub=sub, email="legacy-metrics@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    cid = str(uuid.uuid4())

    create = client.post(
        "/api/v1/workouts",
        json={
            "client_id": cid,
            "date": "2026-10-01",
            "workout_type": "strength",
            "sets": [
                {
                    "exercise_name": "Bench Press",
                    "set_number": 1,
                    "reps": 8,
                    "weight": 135,
                },
            ],
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    workout_id = create.json()["id"]

    factory = get_session_factory()
    assert factory is not None
    async with factory() as session:
        user = (
            await session.execute(select(User).where(User.supabase_id == sub))
        ).scalar_one()
        workout = (
            await session.execute(
                select(Workout)
                .where(Workout.id == workout_id, Workout.user_id == user.id)
                .options(selectinload(Workout.exercise_sets))
            )
        ).scalar_one()
        await session.execute(delete(DerivedMetrics).where(DerivedMetrics.workout_id == workout.id))
        await session.commit()

    get_one = client.get(f"/api/v1/workouts/{workout_id}", headers=headers)
    assert get_one.status_code == 200, get_one.text
    assert get_one.json()["metrics"] is not None
    assert get_one.json()["metrics"]["total_volume"] == 8 * 135
    assert get_one.json()["metrics"]["total_sets"] == 1

    lst = client.get("/api/v1/workouts?page=1&per_page=20", headers=headers)
    assert lst.status_code == 200
    found = next(i for i in lst.json()["items"] if i["id"] == workout_id)
    assert found["metrics"] is not None
    assert found["metrics"]["total_volume"] == 8 * 135


@pytest.mark.asyncio
async def test_workouts_duplicate_client_id(client: TestClient) -> None:
    sub = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    token = _encode_claims(sub=sub, email="dup@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    cid = str(uuid.uuid4())
    body = {
        "client_id": cid,
        "date": "2026-05-01",
        "workout_type": "cardio",
        "sets": [],
    }
    assert client.post("/api/v1/workouts", json=body, headers=headers).status_code == 201
    r2 = client.post("/api/v1/workouts", json=body, headers=headers)
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "duplicate_client_id"


@pytest.mark.asyncio
async def test_workouts_pagination_filters_and_soft_delete_hidden(
    client: TestClient,
) -> None:
    sub = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    token = _encode_claims(sub=sub, email="page@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    for d, wtype in (
        (date(2026, 6, 1), "strength"),
        (date(2026, 6, 2), "strength"),
        (date(2026, 6, 3), "cardio"),
        (date(2026, 6, 4), "strength"),
        (date(2026, 6, 5), "strength"),
    ):
        r = client.post(
            "/api/v1/workouts",
            json={
                "client_id": str(uuid.uuid4()),
                "date": d.isoformat(),
                "workout_type": wtype,
                "sets": [],
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text

    lst = client.get(
        "/api/v1/workouts?page=1&per_page=2&workout_type=strength&order_by=date&order_dir=desc",
        headers=headers,
    )
    assert lst.status_code == 200
    data = lst.json()
    assert data["total"] == 4
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["per_page"] == 2

    p2 = client.get(
        "/api/v1/workouts?page=2&per_page=2&workout_type=strength&order_by=date&order_dir=desc",
        headers=headers,
    )
    assert p2.status_code == 200
    assert len(p2.json()["items"]) == 2

    to_remove_id = data["items"][0]["id"]
    assert client.delete(f"/api/v1/workouts/{to_remove_id}", headers=headers).status_code == 204

    after = client.get(
        "/api/v1/workouts?page=1&per_page=10&workout_type=strength",
        headers=headers,
    )
    assert after.json()["total"] == 3
    assert client.get(f"/api/v1/workouts/{to_remove_id}", headers=headers).status_code == 404


@pytest.mark.asyncio
async def test_workouts_list_invalid_query_returns_422(client: TestClient) -> None:
    token = _encode_claims(sub="abababab-abab-abab-abab-abababababab", email="badq@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get("/api/v1/workouts?order_by=invalid", headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_workouts_update_can_clear_notes_with_null(client: TestClient) -> None:
    token = _encode_claims(sub="cdcdcdcd-cdcd-cdcd-cdcd-cdcdcdcdcdcd", email="clear@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    create = client.post(
        "/api/v1/workouts",
        json={
            "client_id": str(uuid.uuid4()),
            "date": "2026-08-01",
            "workout_type": "strength",
            "notes": "needs clearing",
            "sets": [],
        },
        headers=headers,
    )
    assert create.status_code == 201, create.text
    workout_id = create.json()["id"]

    update = client.put(
        f"/api/v1/workouts/{workout_id}",
        json={"notes": None},
        headers=headers,
    )
    assert update.status_code == 200, update.text
    assert update.json()["notes"] is None


@pytest.mark.asyncio
async def test_workouts_user_isolation(client: TestClient) -> None:
    t_a = _encode_claims(
        sub="11111111-1111-1111-1111-111111111111",
        email="a_iso@example.com",
    )
    t_b = _encode_claims(
        sub="22222222-2222-2222-2222-222222222222",
        email="b_iso@example.com",
    )
    cid = str(uuid.uuid4())
    c = client.post(
        "/api/v1/workouts",
        json={
            "client_id": cid,
            "date": "2026-07-01",
            "workout_type": "other",
            "sets": [],
        },
        headers={"Authorization": f"Bearer {t_a}"},
    )
    assert c.status_code == 201
    wid = c.json()["id"]

    other = client.get(
        f"/api/v1/workouts/{wid}",
        headers={"Authorization": f"Bearer {t_b}"},
    )
    assert other.status_code == 404
    assert other.json()["detail"]["code"] == "workout_not_found"
