"""Unit tests for sync Pydantic schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.domains.sync.schemas import (
    EntityType,
    OperationType,
    SyncChange,
    SyncRequest,
    SyncResponse,
    SyncStatusResponse,
)


def test_sync_change_defaults_and_enums() -> None:
    cid = uuid.uuid4()
    ts = datetime.now(UTC)
    c = SyncChange(
        operation=OperationType.CREATE,
        entity=EntityType.WORKOUT,
        client_id=cid,
        client_timestamp=ts,
    )
    assert c.data == {}
    assert c.operation == "create"
    assert c.entity == "workout"


def test_sync_request_accepts_empty_changes() -> None:
    r = SyncRequest(last_sync_at=None, changes=[])
    assert r.changes == []


def test_sync_response_roundtrip() -> None:
    ts = datetime.now(UTC)
    cid = uuid.uuid4()
    r = SyncResponse(
        sync_timestamp=ts,
        applied=[cid],
        conflicts=[],
        server_changes=[],
    )
    dumped = r.model_dump(mode="json")
    r2 = SyncResponse.model_validate(dumped)
    assert r2.applied == [cid]


def test_sync_status_response() -> None:
    ts = datetime.now(UTC)
    s = SyncStatusResponse(last_sync_at=ts)
    assert s.last_sync_at == ts


def test_sync_change_rejects_naive_client_timestamp() -> None:
    with pytest.raises(ValueError):
        SyncChange(
            operation=OperationType.CREATE,
            entity=EntityType.WORKOUT,
            client_id=uuid.uuid4(),
            client_timestamp=datetime(2026, 5, 1, 12, 0, 0),
        )


def test_sync_request_rejects_naive_last_sync_at() -> None:
    with pytest.raises(ValueError):
        SyncRequest(
            last_sync_at=datetime(2026, 5, 1, 12, 0, 0),
            changes=[],
        )


def test_sync_request_limits_change_batch_size() -> None:
    base_ts = datetime.now(UTC)
    too_many = [
        SyncChange(
            operation=OperationType.CREATE,
            entity=EntityType.WORKOUT,
            client_id=uuid.uuid4(),
            client_timestamp=base_ts,
            data={"date": "2026-05-01", "workout_type": "strength", "sets": []},
        )
        for _ in range(501)
    ]
    with pytest.raises(ValueError):
        SyncRequest(changes=too_many)
