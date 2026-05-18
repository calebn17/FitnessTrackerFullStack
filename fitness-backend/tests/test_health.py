"""Health endpoint smoke test."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.main as main_module
from app.dependencies import get_db_session
from app.main import create_app


@pytest.mark.usefixtures("migrated_database")
def test_health_ok() -> None:
    client = TestClient(main_module.app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"


def test_health_unhealthy_when_database_check_fails() -> None:
    async def bad_session() -> AsyncGenerator[AsyncSession, None]:
        mock = MagicMock(spec=AsyncSession)
        mock.execute = AsyncMock(side_effect=OSError("db down"))
        yield mock

    app = create_app()
    app.dependency_overrides[get_db_session] = bad_session
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["database"]["status"] == "error"
