"""Unit tests for Strava API client."""

import httpx
import pytest

from app.core.oauth import ProviderAuthExpiredError
from app.domains.activities.strava_client import (
    StravaClient,
    StravaRateLimitedError,
    parse_strava_activity,
)


@pytest.mark.asyncio
async def test_fetch_all_running_activities_filters_and_paginates() -> None:
    pages = {
        1: [
            {"id": 1, "sport_type": "Run", "start_date_local": "2026-05-01T07:00:00Z"},
            {"id": 2, "sport_type": "Ride", "start_date_local": "2026-05-02T07:00:00Z"},
        ],
        2: [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json=pages.get(page, []))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = StravaClient(http)
        items = await client.fetch_all_running_activities("token")
    assert len(items) == 1
    assert items[0]["id"] == 1


@pytest.mark.asyncio
async def test_list_activities_rate_limited() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(429))
    async with httpx.AsyncClient(transport=transport) as http:
        client = StravaClient(http)
        with pytest.raises(StravaRateLimitedError):
            await client.list_activities("token")


@pytest.mark.asyncio
async def test_list_activities_auth_expired() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(401))
    async with httpx.AsyncClient(transport=transport) as http:
        client = StravaClient(http)
        with pytest.raises(ProviderAuthExpiredError):
            await client.list_activities("token")


def test_parse_strava_activity_maps_fields() -> None:
    parsed = parse_strava_activity(
        {
            "id": 99,
            "sport_type": "TrailRun",
            "start_date_local": "2026-05-20T07:30:00+00:00",
            "distance": 5000.0,
            "moving_time": 1800,
            "elapsed_time": 1900,
            "average_speed": 2.5,
            "total_elevation_gain": 100.0,
            "pr_count": 1,
        },
    )
    assert parsed["strava_id"] == 99
    assert parsed["sport_type"] == "TrailRun"
    assert parsed["moving_time"] == 1800
