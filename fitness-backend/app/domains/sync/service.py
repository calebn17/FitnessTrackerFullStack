"""Sync business logic (Phase 6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sync.schemas import (
    EntityType,
    OperationType,
    ServerChange,
    SyncChange,
    SyncConflict,
    SyncRequest,
    SyncResponse,
    SyncStatusResponse,
)
from app.domains.users.service import UserService
from app.domains.workouts.models import Workout
from app.domains.workouts.repository import WorkoutRepository
from app.domains.workouts.schemas import WorkoutCreate, WorkoutUpdate
from app.domains.workouts.service import _exercise_set_from_create, serialize_workout_read


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _server_version_timestamp(workout: Workout) -> datetime:
    """Monotonic-ish server version time for last-write-wins (excludes pending deletes)."""
    if workout.updated_at is not None:
        return workout.updated_at
    return workout.created_at


def _is_server_newer(workout: Workout, client_ts: datetime) -> bool:
    return _server_version_timestamp(workout) > client_ts


def _workout_to_server_change(workout: Workout, since: datetime) -> ServerChange:
    """Describe how the client should reconcile one row the server changed after ``since``."""
    if workout.deleted_at is not None and workout.deleted_at > since:
        return ServerChange(
            entity=EntityType.WORKOUT,
            operation=OperationType.DELETE,
            client_id=workout.client_id,
            server_timestamp=workout.deleted_at,
            data={
                "id": str(workout.id),
                "client_id": str(workout.client_id) if workout.client_id else None,
            },
        )
    if workout.created_at > since:
        return ServerChange(
            entity=EntityType.WORKOUT,
            operation=OperationType.CREATE,
            client_id=workout.client_id,
            server_timestamp=workout.created_at,
            data=serialize_workout_read(workout).model_dump(mode="json"),
        )
    op_ts = workout.updated_at if workout.updated_at is not None else workout.created_at
    return ServerChange(
        entity=EntityType.WORKOUT,
        operation=OperationType.UPDATE,
        client_id=workout.client_id,
        server_timestamp=op_ts,
        data=serialize_workout_read(workout).model_dump(mode="json"),
    )


class SyncService:
    """Applies batched offline changes and returns server-side updates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._workouts = WorkoutRepository(session)

    async def _user_id(self, claims: dict[str, Any]) -> uuid.UUID:
        try:
            user = await UserService(self._session).get_or_create_from_supabase(claims)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_user_claims", "errors": exc.errors()},
            ) from exc
        return user.id

    def _parse_workout_create(self, change: SyncChange) -> WorkoutCreate:
        data = dict(change.data)
        data["client_id"] = change.client_id
        return WorkoutCreate.model_validate(data)

    async def _apply_create(
        self,
        user_id: uuid.UUID,
        change: SyncChange,
        applied: list[uuid.UUID],
        conflicts: list[SyncConflict],
    ) -> None:
        existing = await self._workouts.get_by_client_id_for_user(
            change.client_id,
            user_id,
            load_children=True,
            include_deleted=True,
        )
        if existing is not None:
            applied.append(change.client_id)
            return

        try:
            payload = self._parse_workout_create(change)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_sync_payload", "errors": exc.errors()},
            ) from exc

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
        applied.append(change.client_id)

    async def _apply_update(
        self,
        user_id: uuid.UUID,
        change: SyncChange,
        applied: list[uuid.UUID],
        conflicts: list[SyncConflict],
    ) -> None:
        existing = await self._workouts.get_by_client_id_for_user(
            change.client_id,
            user_id,
            load_children=True,
            include_deleted=True,
        )
        if existing is None:
            try:
                payload = self._parse_workout_create(change)
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={"code": "invalid_sync_payload", "errors": exc.errors()},
                ) from exc
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
            applied.append(change.client_id)
            return

        if existing.deleted_at is not None:
            conflicts.append(
                SyncConflict(
                    client_id=change.client_id,
                    entity=EntityType.WORKOUT,
                    server_version=serialize_workout_read(existing).model_dump(mode="json"),
                ),
            )
            return

        if _is_server_newer(existing, change.client_timestamp):
            conflicts.append(
                SyncConflict(
                    client_id=change.client_id,
                    entity=EntityType.WORKOUT,
                    server_version=serialize_workout_read(existing).model_dump(mode="json"),
                ),
            )
            return

        try:
            update_payload = WorkoutUpdate.model_validate(change.data)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "invalid_sync_payload", "errors": exc.errors()},
            ) from exc

        now = _utcnow()
        if update_payload.date is not None:
            existing.date = update_payload.date
        if update_payload.workout_type is not None:
            existing.workout_type = update_payload.workout_type
        if "notes" in update_payload.model_fields_set:
            existing.notes = update_payload.notes
        if update_payload.sets is not None:
            new_sets = [_exercise_set_from_create(s) for s in update_payload.sets]
            await self._workouts.replace_exercise_sets(existing, new_sets)
            await self._workouts.refresh_derived_metrics(existing)
        elif existing.derived_metrics is None:
            await self._workouts.refresh_derived_metrics(existing)
        existing.updated_at = now
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "duplicate_client_id", "message": "Conflict while saving workout."},
            ) from exc
        applied.append(change.client_id)

    async def _apply_delete(
        self,
        user_id: uuid.UUID,
        change: SyncChange,
        applied: list[uuid.UUID],
        conflicts: list[SyncConflict],
    ) -> None:
        existing = await self._workouts.get_by_client_id_for_user(
            change.client_id,
            user_id,
            load_children=True,
            include_deleted=True,
        )
        if existing is None or existing.deleted_at is not None:
            applied.append(change.client_id)
            return
        if _is_server_newer(existing, change.client_timestamp):
            conflicts.append(
                SyncConflict(
                    client_id=change.client_id,
                    entity=EntityType.WORKOUT,
                    server_version=serialize_workout_read(existing).model_dump(mode="json"),
                ),
            )
            return
        await self._workouts.soft_delete_workout(existing, when=_utcnow())
        await self._session.commit()
        applied.append(change.client_id)

    async def process_sync(self, claims: dict[str, Any], request: SyncRequest) -> SyncResponse:
        user_id = await self._user_id(claims)
        applied: list[uuid.UUID] = []
        conflicts: list[SyncConflict] = []

        for change in request.changes:
            if change.entity != EntityType.WORKOUT:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "code": "unsupported_sync_entity",
                        "entity": change.entity.value,
                        "message": "Only workout aggregate sync is supported in v1.",
                    },
                )
            if change.operation is OperationType.CREATE:
                await self._apply_create(user_id, change, applied, conflicts)
            elif change.operation is OperationType.UPDATE:
                await self._apply_update(user_id, change, applied, conflicts)
            else:
                await self._apply_delete(user_id, change, applied, conflicts)

        server_changes: list[ServerChange] = []
        if request.last_sync_at is not None:
            rows = await self._workouts.list_changed_since_for_user(
                user_id,
                request.last_sync_at,
                load_children=True,
            )
            server_changes = [_workout_to_server_change(w, request.last_sync_at) for w in rows]

        return SyncResponse(
            sync_timestamp=_utcnow(),
            applied=applied,
            conflicts=conflicts,
            server_changes=server_changes,
        )

    async def sync_status(self, claims: dict[str, Any]) -> SyncStatusResponse:
        await self._user_id(claims)
        return SyncStatusResponse(last_sync_at=_utcnow())
