"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings, get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    """Return the shared async engine (lazy singleton)."""
    global _engine
    if _engine is None:
        cfg = settings or get_settings()
        _engine = create_async_engine(cfg.database_url, echo=cfg.debug)
    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Return the shared async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = _make_session_factory(get_engine(settings))
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose engine (shutdown hooks / tests)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def reset_database_singletons() -> None:
    """Clear cached engine/session factory without disposing (tests may replace URL next)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None


async def init_database_engine(settings: Settings | None = None) -> None:
    """Initialize singleton engine and session factory from settings."""
    global _engine, _session_factory
    await dispose_engine()
    cfg = settings or get_settings()
    _engine = create_async_engine(cfg.database_url, echo=cfg.debug)
    _session_factory = _make_session_factory(_engine)
