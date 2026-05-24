"""Unit tests for Strava activity service sync logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.domains.activities.models import PROVIDER_STRAVA
from app.domains.activities.repository import OAuthTokenRepository
from app.domains.activities.service import ActivityService
from app.domains.activities.strava_client import StravaClient
from app.domains.users.repository import UserRepository


@pytest.mark.asyncio
async def test_sync_if_stale_skips_when_fresh(db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="strava-sync-sub", email="strava-sync@example.com")
    tokens = OAuthTokenRepository(db_session)
    await tokens.upsert(
        user_id=user.id,
        provider=PROVIDER_STRAVA,
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    token = await tokens.get_for_user_provider(user.id, PROVIDER_STRAVA)
    assert token is not None
    token.last_synced_at = datetime.now(UTC)
    await db_session.commit()

    mock_client = AsyncMock(spec=StravaClient)
    service = ActivityService(
        db_session,
        Settings(strava_client_id="id", strava_client_secret="secret", sync_staleness_minutes=15),
        strava_client=mock_client,
    )
    synced = await service.sync_if_stale(user.id)
    mock_client.fetch_all_running_activities.assert_not_called()
    assert synced is not None


@pytest.mark.asyncio
async def test_sync_if_stale_fetches_when_stale(db_session: AsyncSession) -> None:
    users = UserRepository(db_session)
    user = await users.create(supabase_id="strava-stale-sub", email="strava-stale@example.com")
    tokens = OAuthTokenRepository(db_session)
    await tokens.upsert(
        user_id=user.id,
        provider=PROVIDER_STRAVA,
        access_token="access",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=2),
    )
    await db_session.commit()

    mock_client = AsyncMock(spec=StravaClient)
    mock_client.fetch_all_running_activities.return_value = [
        {
            "id": 1001,
            "sport_type": "Run",
            "start_date_local": "2026-05-20T07:30:00+00:00",
            "distance": 5000.0,
            "moving_time": 1800,
            "elapsed_time": 1900,
            "average_speed": 2.5,
            "total_elevation_gain": 50.0,
        },
    ]
    service = ActivityService(
        db_session,
        Settings(
            strava_client_id="id",
            strava_client_secret="secret",
            supabase_jwt_secret="x" * 32,
            sync_staleness_minutes=15,
        ),
        strava_client=mock_client,
    )
    await service.sync_if_stale(user.id)
    mock_client.fetch_all_running_activities.assert_awaited_once()


@pytest.mark.asyncio
async def test_activity_service_closes_owned_client(db_session: AsyncSession) -> None:
    mock_client = AsyncMock(spec=StravaClient)
    service = ActivityService(
        db_session,
        Settings(strava_client_id="id", strava_client_secret="secret"),
        strava_client=mock_client,
    )

    await service.aclose()

    mock_client.aclose.assert_awaited_once()
