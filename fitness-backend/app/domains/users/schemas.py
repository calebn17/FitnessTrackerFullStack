"""Pydantic schemas for users (Phase 2+)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class SupabaseUserClaims(BaseModel):
    """JWT claims required to provision or load a local user row."""

    model_config = ConfigDict(extra="ignore")

    sub: str
    email: str

    @field_validator("sub", "email")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "Value must not be empty."
            raise ValueError(msg)
        return stripped


class UserRead(BaseModel):
    """Serialized user returned from the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    supabase_id: str
    email: str
    created_at: datetime
    updated_at: datetime | None

