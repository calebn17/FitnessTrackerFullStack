"""User HTTP routes (Phase 3+)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.rate_limit import configured_read_limit, limiter
from app.dependencies import get_db_session, get_supabase_jwt_claims
from app.domains.users.schemas import UserRead
from app.domains.users.service import UserService

router = APIRouter(prefix="/users", tags=["users"])


async def _get_me_user(
    claims: dict[str, Any],
    session: AsyncSession,
) -> UserRead:
    try:
        user = await UserService(session).get_or_create_from_supabase(claims)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_user_claims", "errors": exc.errors()},
        ) from exc
    return UserRead.model_validate(user)


@router.get("/me", response_model=UserRead)
@limiter.limit(configured_read_limit)
async def read_current_user(
    request: Request,
    response: Response,
    claims: Annotated[dict[str, Any], Depends(get_supabase_jwt_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserRead:
    """Return the authenticated user profile, provisioning the row on first request."""
    return await _get_me_user(claims, session)

