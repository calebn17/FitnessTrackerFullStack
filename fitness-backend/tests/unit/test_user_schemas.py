"""Unit tests for user Pydantic schemas (Phase 8 bounds)."""

import pytest
from pydantic import ValidationError

from app.domains.users.schemas import SupabaseUserClaims


def test_supabase_user_claims_accepts_typical_sub_and_email() -> None:
    c = SupabaseUserClaims(
        sub="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        email="user@example.com",
    )
    assert c.sub == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_supabase_user_claims_rejects_overlong_sub() -> None:
    with pytest.raises(ValidationError):
        SupabaseUserClaims(sub="x" * 200, email="a@b.co")


def test_supabase_user_claims_rejects_overlong_email() -> None:
    with pytest.raises(ValidationError):
        SupabaseUserClaims(sub="sub-ok", email=("x" * 400) + "@example.com")
