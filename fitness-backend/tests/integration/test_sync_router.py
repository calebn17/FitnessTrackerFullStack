"""Integration tests for /api/v1/sync routes (Postgres + migrations)."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings, get_settings
from app.dependencies import get_db_session
from app.domains.ai import models as _ai_models  # noqa: F401
from app.domains.workouts import models as _workout_models  # noqa: F401
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
        "email": "sync-router@example.com",
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
async def test_sync_post_unauthorized(client: TestClient) -> None:
    r = client.post("/api/v1/sync", json={"changes": []})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_sync_post_missing_email_claims_returns_422(client: TestClient) -> None:
    token = _encode_claims(sub="44444444-4444-4444-4444-444444444444", email=None)
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post("/api/v1/sync", json={"changes": []}, headers=headers)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invalid_user_claims"


@pytest.mark.asyncio
async def test_sync_status_returns_timestamp(client: TestClient) -> None:
    token = _encode_claims()
    r = client.get("/api/v1/sync/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert "last_sync_at" in body
    datetime.fromisoformat(body["last_sync_at"].replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_sync_router_create_and_duplicate(client: TestClient) -> None:
    sub = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    token = _encode_claims(sub=sub, email="sync-crud@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    cid = str(uuid.uuid4())
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    body = {
        "changes": [
            {
                "operation": "create",
                "entity": "workout",
                "client_id": cid,
                "client_timestamp": ts,
                "data": {
                    "date": "2026-07-01",
                    "workout_type": "strength",
                    "sets": [
                        {
                            "exercise_name": "Press",
                            "set_number": 1,
                            "reps": 8,
                            "weight": 95,
                        },
                    ],
                },
            },
        ],
    }
    c1 = client.post("/api/v1/sync", json=body, headers=headers)
    assert c1.status_code == 200, c1.text
    assert cid in c1.json()["applied"]
    c2 = client.post("/api/v1/sync", json=body, headers=headers)
    assert c2.status_code == 200
    assert cid in c2.json()["applied"]


@pytest.mark.asyncio
async def test_sync_router_create_ignores_payload_client_id_override(client: TestClient) -> None:
    sub = "abababab-abab-abab-abab-abababababab"
    token = _encode_claims(sub=sub, email="sync-cid-override@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    envelope_cid = str(uuid.uuid4())
    payload_cid = str(uuid.uuid4())
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    r = client.post(
        "/api/v1/sync",
        json={
            "changes": [
                {
                    "operation": "create",
                    "entity": "workout",
                    "client_id": envelope_cid,
                    "client_timestamp": ts,
                    "data": {
                        "client_id": payload_cid,
                        "date": "2026-07-20",
                        "workout_type": "strength",
                        "sets": [],
                    },
                },
            ],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert envelope_cid in r.json()["applied"]
    lst = client.get("/api/v1/workouts?per_page=100", headers=headers)
    assert lst.status_code == 200
    rows = lst.json()["items"]
    assert any(item["client_id"] == envelope_cid for item in rows)
    assert not any(item["client_id"] == payload_cid for item in rows)


@pytest.mark.asyncio
async def test_sync_router_rejects_naive_timestamps(client: TestClient) -> None:
    token = _encode_claims(
        sub="cececece-cece-cece-cece-cececececece",
        email="sync-naive-ts@example.com",
    )
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/api/v1/sync",
        json={
            "last_sync_at": "2026-07-01T10:00:00",
            "changes": [
                {
                    "operation": "create",
                    "entity": "workout",
                    "client_id": str(uuid.uuid4()),
                    "client_timestamp": "2026-07-01T10:00:00",
                    "data": {"date": "2026-07-21", "workout_type": "strength", "sets": []},
                },
            ],
        },
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_sync_router_update_conflict_delete_and_server_changes(client: TestClient) -> None:
    sub = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    token = _encode_claims(sub=sub, email="sync-flow@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    cid = str(uuid.uuid4())

    create_ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    client.post(
        "/api/v1/sync",
        json={
            "changes": [
                {
                    "operation": "create",
                    "entity": "workout",
                    "client_id": cid,
                    "client_timestamp": create_ts,
                    "data": {
                        "date": "2026-07-15",
                        "workout_type": "flexibility",
                        "sets": [],
                    },
                },
            ],
        },
        headers=headers,
    )

    upd_ok = client.post(
        "/api/v1/sync",
        json={
            "changes": [
                {
                    "operation": "update",
                    "entity": "workout",
                    "client_id": cid,
                    "client_timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "data": {"notes": "from sync"},
                },
            ],
        },
        headers=headers,
    )
    assert upd_ok.status_code == 200
    assert cid in upd_ok.json()["applied"]

    lst = client.get("/api/v1/workouts?per_page=50", headers=headers)
    assert lst.status_code == 200
    wid = next(i["id"] for i in lst.json()["items"] if i["client_id"] == cid)
    client.put(
        f"/api/v1/workouts/{wid}",
        json={"notes": "server updated"},
        headers=headers,
    )

    conflict = client.post(
        "/api/v1/sync",
        json={
            "changes": [
                {
                    "operation": "update",
                    "entity": "workout",
                    "client_id": cid,
                    "client_timestamp": "2019-01-01T00:00:00Z",
                    "data": {"notes": "stale"},
                },
            ],
        },
        headers=headers,
    )
    assert conflict.status_code == 200
    assert cid not in conflict.json()["applied"]
    assert len(conflict.json()["conflicts"]) == 1

    del_resp = client.post(
        "/api/v1/sync",
        json={
            "changes": [
                {
                    "operation": "delete",
                    "entity": "workout",
                    "client_id": cid,
                    "client_timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "data": {},
                },
            ],
        },
        headers=headers,
    )
    assert del_resp.status_code == 200
    assert cid in del_resp.json()["applied"]
    gone = client.get(f"/api/v1/workouts/{wid}", headers=headers)
    assert gone.status_code == 404

    anchor = (datetime.now(UTC) - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    other_cid = str(uuid.uuid4())
    bootstrap = client.post(
        "/api/v1/sync",
        json={
            "last_sync_at": anchor,
            "changes": [
                {
                    "operation": "create",
                    "entity": "workout",
                    "client_id": other_cid,
                    "client_timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "data": {
                        "date": "2026-08-01",
                        "workout_type": "other",
                        "sets": [],
                    },
                },
            ],
        },
        headers=headers,
    )
    assert bootstrap.status_code == 200
    assert any(
        ch.get("operation") == "create" and ch.get("entity") == "workout"
        for ch in bootstrap.json()["server_changes"]
    )
