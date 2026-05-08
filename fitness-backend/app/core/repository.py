"""Shared repository helpers."""

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Thin base providing common access to the async SQLAlchemy session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @property
    def session(self) -> AsyncSession:
        return self._session
