"""User persistence."""

import uuid

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domains.users.models import User


class UserRepository(BaseRepository):
    """CRUD-style access for `User` rows."""

    async def create(self, *, supabase_id: str, email: str) -> User:
        user = User(supabase_id=supabase_id, email=email)
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_supabase_id(self, supabase_id: str) -> User | None:
        stmt = select(User).where(User.supabase_id == supabase_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
