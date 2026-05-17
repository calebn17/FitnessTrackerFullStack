"""User business logic (Phase 3+)."""

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.users.models import User
from app.domains.users.repository import UserRepository
from app.domains.users.schemas import SupabaseUserClaims


class UserService:
    """Coordinates user persistence for auth-backed flows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)

    async def _sync_email_if_needed(self, user: User, email: str) -> User:
        if user.email == email:
            return user
        user.email = email
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            # Another row already owns this email; keep existing user/email untouched.
            return user
        return user

    async def get_or_create_from_supabase(self, claims: dict[str, Any]) -> User:
        """Return the user for this Supabase subject, creating the row on first sight."""
        parsed = SupabaseUserClaims.model_validate(claims)
        sub = parsed.sub
        email = parsed.email

        existing = await self._users.get_by_supabase_id(sub)
        if existing is not None:
            return await self._sync_email_if_needed(existing, email)

        try:
            user = await self._users.create(supabase_id=sub, email=email)
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            raced = await self._users.get_by_supabase_id(sub)
            if raced is not None:
                return await self._sync_email_if_needed(raced, email)

            email_owner = await self._users.get_by_email(email)
            if email_owner is not None:
                return email_owner
            raise

        return user
