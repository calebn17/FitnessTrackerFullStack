"""Tests for SyncService (Postgres + migrations)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.domains.sync.schemas import EntityType, OperationType, SyncChange, SyncRequest
from app.domains.sync.service import SyncService
from app.domains.users.repository import UserRepository
from app.domains.workouts.repository import WorkoutRepository


@pytest.mark.asyncio
async def test_sync_service_create_workout(db_session) -> None:
    users = UserRepository(db_session)
    await users.create(supabase_id="sync-svc-1", email="sync-svc-1@example.com")
    await db_session.commit()
    claims = {"sub": "sync-svc-1", "email": "sync-svc-1@example.com"}
    cid = uuid.uuid4()
    ts = datetime.now(UTC)
    req = SyncRequest(
        changes=[
            SyncChange(
                operation=OperationType.CREATE,
                entity=EntityType.WORKOUT,
                client_id=cid,
                client_timestamp=ts,
                data={
                    "date": "2026-05-01",
                    "workout_type": "strength",
                    "sets": [],
                },
            ),
        ],
    )
    out = await SyncService(db_session).process_sync(claims, req)
    assert cid in out.applied
    assert not out.conflicts

    user = await users.get_by_supabase_id("sync-svc-1")
    assert user is not None
    row = await WorkoutRepository(db_session).get_by_client_id_for_user(
        cid,
        user.id,
        load_children=True,
    )
    assert row is not None
    assert row.date == date(2026, 5, 1)


@pytest.mark.asyncio
async def test_sync_service_duplicate_create_idempotent(db_session) -> None:
    users = UserRepository(db_session)
    await users.create(supabase_id="sync-svc-2", email="sync-svc-2@example.com")
    await db_session.commit()
    claims = {"sub": "sync-svc-2", "email": "sync-svc-2@example.com"}
    cid = uuid.uuid4()
    ts = datetime.now(UTC)
    body = {
        "date": "2026-05-02",
        "workout_type": "strength",
        "sets": [],
    }
    req = SyncRequest(
        changes=[
            SyncChange(
                operation=OperationType.CREATE,
                entity=EntityType.WORKOUT,
                client_id=cid,
                client_timestamp=ts,
                data=body,
            ),
        ],
    )
    out1 = await SyncService(db_session).process_sync(claims, req)
    assert cid in out1.applied
    out2 = await SyncService(db_session).process_sync(claims, req)
    assert cid in out2.applied
    user = await users.get_by_supabase_id("sync-svc-2")
    assert user is not None
    found = await WorkoutRepository(db_session).get_by_client_id_for_user(cid, user.id)
    assert found is not None


@pytest.mark.asyncio
async def test_sync_service_update_and_conflict(db_session) -> None:
    users = UserRepository(db_session)
    await users.create(supabase_id="sync-svc-3", email="sync-svc-3@example.com")
    await db_session.commit()
    claims = {"sub": "sync-svc-3", "email": "sync-svc-3@example.com"}
    cid = uuid.uuid4()
    ts = datetime.now(UTC)
    await SyncService(db_session).process_sync(
        claims,
        SyncRequest(
            changes=[
                SyncChange(
                    operation=OperationType.CREATE,
                    entity=EntityType.WORKOUT,
                    client_id=cid,
                    client_timestamp=ts,
                    data={
                        "date": "2026-05-03",
                        "workout_type": "strength",
                        "sets": [],
                    },
                ),
            ],
        ),
    )

    ok = await SyncService(db_session).process_sync(
        claims,
        SyncRequest(
            changes=[
                SyncChange(
                    operation=OperationType.UPDATE,
                    entity=EntityType.WORKOUT,
                    client_id=cid,
                    client_timestamp=datetime.now(UTC),
                    data={"notes": "client notes"},
                ),
            ],
        ),
    )
    assert cid in ok.applied
    user = await users.get_by_supabase_id("sync-svc-3")
    assert user is not None
    w = await WorkoutRepository(db_session).get_by_client_id_for_user(cid, user.id)
    assert w is not None
    assert w.notes == "client notes"

    await WorkoutRepository(db_session).touch_workout_updated(w, when=datetime.now(UTC))
    await db_session.commit()

    stale = datetime(2018, 1, 1, tzinfo=UTC)
    conflict = await SyncService(db_session).process_sync(
        claims,
        SyncRequest(
            changes=[
                SyncChange(
                    operation=OperationType.UPDATE,
                    entity=EntityType.WORKOUT,
                    client_id=cid,
                    client_timestamp=stale,
                    data={"notes": "should not apply"},
                ),
            ],
        ),
    )
    assert cid not in conflict.applied
    assert len(conflict.conflicts) == 1
    await db_session.refresh(w)
    assert w.notes == "client notes"


@pytest.mark.asyncio
async def test_sync_service_delete(db_session) -> None:
    users = UserRepository(db_session)
    await users.create(supabase_id="sync-svc-4", email="sync-svc-4@example.com")
    await db_session.commit()
    claims = {"sub": "sync-svc-4", "email": "sync-svc-4@example.com"}
    cid = uuid.uuid4()
    await SyncService(db_session).process_sync(
        claims,
        SyncRequest(
            changes=[
                SyncChange(
                    operation=OperationType.CREATE,
                    entity=EntityType.WORKOUT,
                    client_id=cid,
                    client_timestamp=datetime.now(UTC),
                    data={
                        "date": "2026-05-04",
                        "workout_type": "cardio",
                        "sets": [],
                    },
                ),
            ],
        ),
    )
    out = await SyncService(db_session).process_sync(
        claims,
        SyncRequest(
            changes=[
                SyncChange(
                    operation=OperationType.DELETE,
                    entity=EntityType.WORKOUT,
                    client_id=cid,
                    client_timestamp=datetime.now(UTC),
                    data={},
                ),
            ],
        ),
    )
    assert cid in out.applied
    user = await users.get_by_supabase_id("sync-svc-4")
    assert user is not None
    gone = await WorkoutRepository(db_session).get_by_client_id_for_user(
        cid,
        user.id,
        include_deleted=False,
    )
    assert gone is None


@pytest.mark.asyncio
async def test_sync_service_server_changes_since(db_session) -> None:
    users = UserRepository(db_session)
    await users.create(supabase_id="sync-svc-5", email="sync-svc-5@example.com")
    await db_session.commit()
    claims = {"sub": "sync-svc-5", "email": "sync-svc-5@example.com"}
    anchor = datetime.now(UTC) - timedelta(seconds=30)
    workouts = WorkoutRepository(db_session)
    user = await users.get_by_supabase_id("sync-svc-5")
    assert user is not None
    await workouts.create_workout(
        user_id=user.id,
        workout_date=date(2026, 6, 1),
        workout_type="strength",
        client_id=uuid.uuid4(),
    )
    await db_session.commit()

    out = await SyncService(db_session).process_sync(
        claims,
        SyncRequest(last_sync_at=anchor, changes=[]),
    )
    assert len(out.server_changes) >= 1
    assert any(c.operation == OperationType.CREATE for c in out.server_changes)


@pytest.mark.asyncio
async def test_sync_service_create_ignores_payload_client_id_override(db_session) -> None:
    users = UserRepository(db_session)
    await users.create(supabase_id="sync-svc-cid-1", email="sync-svc-cid-1@example.com")
    await db_session.commit()
    claims = {"sub": "sync-svc-cid-1", "email": "sync-svc-cid-1@example.com"}
    envelope_cid = uuid.uuid4()
    payload_cid = uuid.uuid4()

    out = await SyncService(db_session).process_sync(
        claims,
        SyncRequest(
            changes=[
                SyncChange(
                    operation=OperationType.CREATE,
                    entity=EntityType.WORKOUT,
                    client_id=envelope_cid,
                    client_timestamp=datetime.now(UTC),
                    data={
                        "client_id": str(payload_cid),
                        "date": "2026-05-10",
                        "workout_type": "strength",
                        "sets": [],
                    },
                ),
            ],
        ),
    )
    assert envelope_cid in out.applied
    user = await users.get_by_supabase_id("sync-svc-cid-1")
    assert user is not None
    stored = await WorkoutRepository(db_session).get_by_client_id_for_user(envelope_cid, user.id)
    assert stored is not None
    leaked = await WorkoutRepository(db_session).get_by_client_id_for_user(payload_cid, user.id)
    assert leaked is None


@pytest.mark.asyncio
async def test_sync_service_missing_email_claims_returns_422(db_session) -> None:
    with pytest.raises(HTTPException) as exc:
        await SyncService(db_session).process_sync(
            claims={"sub": "missing-email-claim"},
            request=SyncRequest(changes=[]),
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "invalid_user_claims"


@pytest.mark.asyncio
async def test_sync_service_duplicate_create_after_soft_delete_is_idempotent(db_session) -> None:
    users = UserRepository(db_session)
    await users.create(supabase_id="sync-svc-soft-dup", email="sync-svc-soft-dup@example.com")
    await db_session.commit()
    claims = {"sub": "sync-svc-soft-dup", "email": "sync-svc-soft-dup@example.com"}
    cid = uuid.uuid4()
    service = SyncService(db_session)
    await service.process_sync(
        claims,
        SyncRequest(
            changes=[
                SyncChange(
                    operation=OperationType.CREATE,
                    entity=EntityType.WORKOUT,
                    client_id=cid,
                    client_timestamp=datetime.now(UTC),
                    data={"date": "2026-05-11", "workout_type": "strength", "sets": []},
                ),
            ],
        ),
    )
    await service.process_sync(
        claims,
        SyncRequest(
            changes=[
                SyncChange(
                    operation=OperationType.DELETE,
                    entity=EntityType.WORKOUT,
                    client_id=cid,
                    client_timestamp=datetime.now(UTC),
                    data={},
                ),
            ],
        ),
    )

    out = await service.process_sync(
        claims,
        SyncRequest(
            changes=[
                SyncChange(
                    operation=OperationType.CREATE,
                    entity=EntityType.WORKOUT,
                    client_id=cid,
                    client_timestamp=datetime.now(UTC),
                    data={"date": "2026-05-11", "workout_type": "strength", "sets": []},
                ),
            ],
        ),
    )
    assert cid in out.applied
    assert not out.conflicts
