"""Sync Pydantic schemas (Phase 6)."""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_MAX_SYNC_DATA_JSON_BYTES = 120_000
_MAX_SYNC_DATA_TOP_LEVEL_KEYS = 64
_MAX_SETS_IN_SYNC_PAYLOAD = 200


class OperationType(StrEnum):
    """Client intent for a synced entity."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class EntityType(StrEnum):
    """Entities supported by the sync protocol (v1: workout aggregate only)."""

    WORKOUT = "workout"


class SyncChange(BaseModel):
    """One client-originated change in a batch."""

    operation: OperationType
    entity: EntityType
    client_id: UUID
    client_timestamp: datetime
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data")
    @classmethod
    def bound_sync_change_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > _MAX_SYNC_DATA_TOP_LEVEL_KEYS:
            msg = (
                f"sync change data may have at most {_MAX_SYNC_DATA_TOP_LEVEL_KEYS} "
                "top-level keys."
            )
            raise ValueError(msg)
        encoded = json.dumps(value, separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_SYNC_DATA_JSON_BYTES:
            msg = f"sync change data JSON must be at most {_MAX_SYNC_DATA_JSON_BYTES} bytes."
            raise ValueError(msg)
        sets = value.get("sets")
        if isinstance(sets, list) and len(sets) > _MAX_SETS_IN_SYNC_PAYLOAD:
            msg = f"sync change sets list may have at most {_MAX_SETS_IN_SYNC_PAYLOAD} items."
            raise ValueError(msg)
        return value

    @field_validator("client_timestamp")
    @classmethod
    def require_timezone_aware_client_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "client_timestamp must include a timezone offset."
            raise ValueError(msg)
        return value


class SyncRequest(BaseModel):
    """Batch sync payload from a mobile client."""

    last_sync_at: datetime | None = None
    changes: list[SyncChange] = Field(default_factory=list, max_length=500)

    @field_validator("last_sync_at")
    @classmethod
    def require_timezone_aware_last_sync_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            msg = "last_sync_at must include a timezone offset."
            raise ValueError(msg)
        return value


class SyncConflict(BaseModel):
    """A change that was not applied because the server version wins."""

    client_id: UUID
    entity: EntityType
    resolution: str = "server_wins"
    server_version: dict[str, Any]


class ServerChange(BaseModel):
    """A server-side mutation the client should apply since last_sync_at."""

    entity: EntityType
    operation: OperationType
    client_id: UUID | None = None
    server_timestamp: datetime
    data: dict[str, Any]


class SyncResponse(BaseModel):
    """Result of processing a sync batch."""

    sync_timestamp: datetime
    applied: list[UUID]
    conflicts: list[SyncConflict]
    server_changes: list[ServerChange]


class SyncStatusResponse(BaseModel):
    """Suggested cursor for the next sync poll (server clock)."""

    last_sync_at: datetime
