"""Unit tests for Whoop API client."""

from datetime import UTC, datetime

import httpx
import pytest

from app.core.oauth import ProviderAuthExpiredError
from app.domains.health.whoop_client import WhoopClient, WhoopRateLimitedError, cycle_calendar_date


def test_cycle_calendar_date_from_end() -> None:
    assert cycle_calendar_date({"end": "2026-05-20T08:00:00Z"}) is not None


@pytest.mark.asyncio
async def test_list_cycles_paginates() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                200,
                json={"records": [{"id": 1, "score_state": "SCORED"}], "next_token": "t2"},
            )
        return httpx.Response(200, json={"records": [], "next_token": None})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        client = WhoopClient(http)
        rows = await client.list_cycles(
            "token",
            start=datetime(2026, 5, 1, tzinfo=UTC),
            end=datetime(2026, 5, 20, tzinfo=UTC),
        )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_list_sleep_rate_limited() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(429))
    async with httpx.AsyncClient(transport=transport) as http:
        client = WhoopClient(http)
        with pytest.raises(WhoopRateLimitedError):
            await client.list_sleep(
                "token",
                start=datetime(2026, 5, 1, tzinfo=UTC),
                end=datetime(2026, 5, 20, tzinfo=UTC),
            )


@pytest.mark.asyncio
async def test_list_sleep_auth_expired() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(401))
    async with httpx.AsyncClient(transport=transport) as http:
        client = WhoopClient(http)
        with pytest.raises(ProviderAuthExpiredError):
            await client.list_sleep(
                "token",
                start=datetime(2026, 5, 1, tzinfo=UTC),
                end=datetime(2026, 5, 20, tzinfo=UTC),
            )
