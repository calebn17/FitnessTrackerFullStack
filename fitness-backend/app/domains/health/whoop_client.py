"""HTTP client for the Whoop API."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx

from app.core.oauth import ProviderAuthExpiredError

WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"
WHOOP_REVOKE_URL = "https://api.prod.whoop.com/oauth/oauth2/revoke"


class WhoopApiError(Exception):
    """Whoop API returned an unexpected status."""

    def __init__(self, status_code: int, message: str = "") -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message or f"Whoop API error {status_code}")


class WhoopRateLimitedError(WhoopApiError):
    """Whoop returned HTTP 429."""


class WhoopClient:
    """Thin async wrapper around Whoop developer API v2."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _get_paginated(
        self,
        path: str,
        *,
        access_token: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        next_token: str | None = None
        while True:
            query = dict(params or {})
            if next_token:
                query["nextToken"] = next_token
            url = f"{WHOOP_API_BASE}{path}"
            headers = {"Authorization": f"Bearer {access_token}"}
            response = await self._client.get(url, headers=headers, params=query)
            if response.status_code == 429:
                raise WhoopRateLimitedError(429)
            if response.status_code == 401:
                raise ProviderAuthExpiredError("Whoop access token is invalid.")
            if response.status_code >= 500:
                raise WhoopApiError(response.status_code)
            if response.status_code >= 400:
                raise WhoopApiError(response.status_code, response.text)
            payload = response.json()
            records = payload.get("records") or payload.get("items") or []
            if isinstance(records, list):
                collected.extend(records)
            next_token = payload.get("next_token") or payload.get("nextToken")
            if not next_token:
                break
        return collected

    async def list_cycles(
        self,
        access_token: str,
        *,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        return await self._get_paginated(
            "/cycle",
            access_token=access_token,
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )

    async def list_sleep(
        self,
        access_token: str,
        *,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        return await self._get_paginated(
            "/activity/sleep",
            access_token=access_token,
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )

    async def list_recovery(
        self,
        access_token: str,
        *,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        return await self._get_paginated(
            "/recovery",
            access_token=access_token,
            params={
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )

    async def revoke_token(
        self,
        *,
        token: str,
        client_id: str,
        client_secret: str,
    ) -> None:
        data = {
            "token": token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
        response = await self._client.post(WHOOP_REVOKE_URL, data=data)
        if response.status_code >= 500:
            raise WhoopApiError(response.status_code)


def cycle_calendar_date(cycle: dict[str, Any]) -> date | None:
    """Map a Whoop cycle to the calendar date of its end timestamp."""
    end_raw = cycle.get("end") or cycle.get("end_time")
    if end_raw is None:
        return None
    if isinstance(end_raw, str):
        end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
    else:
        return None
    return end_dt.astimezone(UTC).date()


def index_by_cycle_id(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for item in items:
        cycle_id = item.get("cycle_id")
        if cycle_id is not None:
            indexed[int(cycle_id)] = item
    return indexed


def index_sleep_by_cycle(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for item in items:
        cycle_id = item.get("cycle_id")
        if cycle_id is not None:
            indexed[int(cycle_id)] = item
    return indexed
