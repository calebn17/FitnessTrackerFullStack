"""HTTP client for the Strava API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import httpx

from app.core.oauth import ProviderAuthExpiredError

STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_DEAUTHORIZE_URL = "https://www.strava.com/oauth/deauthorize"
RUNNING_SPORT_TYPES = frozenset({"Run", "TrailRun", "VirtualRun"})


class StravaApiError(Exception):
    """Strava API returned an unexpected status."""

    def __init__(self, status_code: int, message: str = "") -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message or f"Strava API error {status_code}")


class StravaRateLimitedError(StravaApiError):
    """Strava returned HTTP 429."""


class StravaClient:
    """Thin async wrapper around Strava REST endpoints."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        access_token: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        url = f"{STRAVA_API_BASE}{path}" if path.startswith("/") else path
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await self._client.request(method, url, headers=headers, params=params)
        if response.status_code == 429:
            raise StravaRateLimitedError(429)
        if response.status_code == 401:
            raise ProviderAuthExpiredError("Strava access token is invalid.")
        if response.status_code >= 500:
            raise StravaApiError(response.status_code)
        if response.status_code >= 400:
            raise StravaApiError(response.status_code, response.text)
        data = response.json()
        if isinstance(data, list):
            return cast(list[dict[str, Any]], data)
        return cast(dict[str, Any], data)

    async def list_activities(
        self,
        access_token: str,
        *,
        after: int | None = None,
        per_page: int = 200,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"per_page": per_page, "page": page}
        if after is not None:
            params["after"] = after
        raw = await self._request(
            "GET",
            "/athlete/activities",
            access_token=access_token,
            params=params,
        )
        return raw if isinstance(raw, list) else []

    async def fetch_all_running_activities(
        self,
        access_token: str,
        *,
        after: int | None = None,
    ) -> list[dict[str, Any]]:
        """Paginate athlete activities and return running sport types only."""
        collected: list[dict[str, Any]] = []
        page = 1
        while True:
            batch = await self.list_activities(
                access_token,
                after=after,
                page=page,
            )
            if not batch:
                break
            for item in batch:
                if item.get("sport_type") in RUNNING_SPORT_TYPES:
                    collected.append(item)
            if len(batch) < 200:
                break
            page += 1
        return collected

    async def deauthorize(self, access_token: str) -> None:
        response = await self._client.post(
            STRAVA_DEAUTHORIZE_URL,
            data={"access_token": access_token},
        )
        if response.status_code >= 500:
            raise StravaApiError(response.status_code)


def parse_strava_activity(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a Strava activity payload to DB column values."""
    start_raw = raw.get("start_date_local") or raw.get("start_date")
    if isinstance(start_raw, str):
        start_date_local = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
    else:
        start_date_local = datetime.now(UTC)
    return {
        "strava_id": int(raw["id"]),
        "sport_type": str(raw.get("sport_type") or "Run"),
        "start_date_local": start_date_local,
        "distance": float(raw.get("distance") or 0.0),
        "moving_time": int(raw.get("moving_time") or 0),
        "elapsed_time": int(raw.get("elapsed_time") or 0),
        "average_speed": float(raw.get("average_speed") or 0.0),
        "max_speed": float(raw["max_speed"]) if raw.get("max_speed") is not None else None,
        "total_elevation_gain": float(raw.get("total_elevation_gain") or 0.0),
        "average_heartrate": (
            float(raw["average_heartrate"]) if raw.get("average_heartrate") is not None else None
        ),
        "max_heartrate": (
            float(raw["max_heartrate"]) if raw.get("max_heartrate") is not None else None
        ),
        "average_cadence": (
            float(raw["average_cadence"]) if raw.get("average_cadence") is not None else None
        ),
        "calories": float(raw["calories"]) if raw.get("calories") is not None else None,
        "pr_count": int(raw.get("pr_count") or 0),
    }
