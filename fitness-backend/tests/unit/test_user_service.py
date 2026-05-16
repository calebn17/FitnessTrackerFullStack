"""Tests for `UserService.get_or_create_from_supabase` (Postgres + migrations)."""

import pytest
from pydantic import ValidationError

from app.domains.users.schemas import UserRead
from app.domains.users.service import UserService


def _claims(sub: str, email: str) -> dict[str, str]:
    return {"sub": sub, "email": email}


@pytest.mark.asyncio
async def test_get_or_create_inserts_first_time(db_session) -> None:
    svc = UserService(db_session)
    user = await svc.get_or_create_from_supabase(_claims("supabase-sub-a", "first@example.com"))

    assert user.supabase_id == "supabase-sub-a"
    assert user.email == "first@example.com"
    assert user.id is not None

    body = UserRead.model_validate(user)
    assert body.email == "first@example.com"
    assert body.supabase_id == "supabase-sub-a"


@pytest.mark.asyncio
async def test_get_or_create_returns_existing_row(db_session) -> None:
    svc = UserService(db_session)
    first = await svc.get_or_create_from_supabase(_claims("supabase-sub-b", "reuse@example.com"))
    second = await svc.get_or_create_from_supabase(_claims("supabase-sub-b", "reuse@example.com"))

    assert second.id == first.id
    assert second.email == "reuse@example.com"


@pytest.mark.asyncio
async def test_get_or_create_syncs_email_for_existing_subject(db_session) -> None:
    svc = UserService(db_session)
    first = await svc.get_or_create_from_supabase(_claims("supabase-sub-c", "old@example.com"))
    second = await svc.get_or_create_from_supabase(_claims("supabase-sub-c", "new@example.com"))

    assert second.id == first.id
    assert second.email == "new@example.com"


@pytest.mark.asyncio
async def test_get_or_create_returns_email_owner_on_conflict(db_session) -> None:
    svc = UserService(db_session)
    owner = await svc.get_or_create_from_supabase(_claims("email-owner", "shared@example.com"))
    conflict = await svc.get_or_create_from_supabase(
        _claims("different-sub", "shared@example.com"),
    )

    assert conflict.id == owner.id
    assert conflict.supabase_id == "email-owner"
    assert conflict.email == "shared@example.com"


@pytest.mark.asyncio
async def test_get_or_create_invalid_claims(db_session) -> None:
    svc = UserService(db_session)
    with pytest.raises(ValidationError):
        await svc.get_or_create_from_supabase({"sub": "", "email": "x@example.com"})
    with pytest.raises(ValidationError):
        await svc.get_or_create_from_supabase({"sub": "sub", "email": "  "})


@pytest.mark.asyncio
async def test_get_or_create_ignores_extra_claims(db_session) -> None:
    svc = UserService(db_session)
    claims = {
        "sub": "supabase-sub-extra",
        "email": "extra@example.com",
        "role": "authenticated",
        "aud": "authenticated",
    }
    user = await svc.get_or_create_from_supabase(claims)
    assert user.supabase_id == "supabase-sub-extra"
