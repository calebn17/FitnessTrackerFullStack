"""Unit tests for Whoop health service lifecycle."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domains.health.service import HealthService
from app.domains.health.whoop_client import WhoopClient


@pytest.mark.asyncio
async def test_health_service_closes_owned_client(db_session: AsyncSession) -> None:
    mock_client = AsyncMock(spec=WhoopClient)
    service = HealthService(
        db_session,
        Settings(whoop_client_id="id", whoop_client_secret="secret"),
        whoop_client=mock_client,
    )

    await service.aclose()

    mock_client.aclose.assert_awaited_once()
