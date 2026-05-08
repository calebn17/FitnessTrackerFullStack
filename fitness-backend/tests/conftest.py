"""Pytest fixtures."""

import os
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.core.database import dispose_engine, get_session_factory, init_database_engine


def _default_database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://fitness:fitness@127.0.0.1:5432/fitness",
    )


@pytest.fixture(scope="session")
def migrated_database() -> None:
    """Apply migrations once per test session."""
    backend_root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": _default_database_url()}
    try:
        subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=str(backend_root),
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "")
        stdout = getattr(exc, "stdout", "")
        pytest.skip(
            "Database migrations failed (start Postgres: docker compose up -d postgres). "
            f"detail={exc!r} stderr={stderr!r} stdout={stdout!r}",
        )


@pytest.fixture
async def db_session(migrated_database: None) -> AsyncGenerator[AsyncSession, None]:
    """Clean database session with tables truncated before each test."""
    settings = Settings(database_url=_default_database_url())
    await init_database_engine(settings)
    factory = get_session_factory(settings)
    async with factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE insights, derived_metrics, exercise_sets, workouts, "
                "users RESTART IDENTITY CASCADE"
            ),
        )
        await session.commit()
        yield session
        await session.rollback()
    await dispose_engine()
