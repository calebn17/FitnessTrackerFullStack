"""Sync HTTP routes (Phase 6)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.rate_limit import configured_read_limit, configured_write_limit, limiter
from app.dependencies import get_db_session, get_supabase_jwt_claims
from app.domains.sync.schemas import SyncRequest, SyncResponse, SyncStatusResponse
from app.domains.sync.service import SyncService

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("", response_model=SyncResponse)
@limiter.limit(configured_write_limit)
async def post_sync(
    request: Request,
    response: Response,
    payload: SyncRequest,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SyncResponse:
    """Apply a batch of offline changes and return server-side updates."""
    return await SyncService(session).process_sync(claims, payload)


@router.get("/status", response_model=SyncStatusResponse)
@limiter.limit(configured_read_limit)
async def get_sync_status(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SyncStatusResponse:
    """Return a server clock cursor clients may use as ``last_sync_at`` on the next poll."""
    return await SyncService(session).sync_status(claims)
