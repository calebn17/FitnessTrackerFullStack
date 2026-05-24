"""Pydantic schemas for Strava activities and OAuth."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Literal
from uuid import UUID

if TYPE_CHECKING:
    from app.domains.activities.models import StravaActivity

from pydantic import BaseModel, ConfigDict, computed_field

METERS_PER_MILE = 1609.344
METERS_PER_FOOT = 0.3048


class OAuthAuthorizeResponse(BaseModel):
    authorization_url: str


class OAuthCallbackResponse(BaseModel):
    provider: str
    connected: bool = True


class StravaActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strava_id: int
    sport_type: str
    start_date_local: datetime
    distance_meters: float
    moving_time_seconds: int
    elapsed_time_seconds: int
    average_speed_mps: float
    max_speed_mps: float | None = None
    total_elevation_gain_meters: float
    average_heartrate: float | None = None
    max_heartrate: float | None = None
    average_cadence: float | None = None
    calories: float | None = None
    pr_count: int = 0

    @classmethod
    def from_model(cls, row: StravaActivity) -> StravaActivityRead:
        activity = row
        return cls(
            id=activity.id,
            strava_id=activity.strava_id,
            sport_type=activity.sport_type,
            start_date_local=activity.start_date_local,
            distance_meters=activity.distance,
            moving_time_seconds=activity.moving_time,
            elapsed_time_seconds=activity.elapsed_time,
            average_speed_mps=activity.average_speed,
            max_speed_mps=activity.max_speed,
            total_elevation_gain_meters=activity.total_elevation_gain,
            average_heartrate=activity.average_heartrate,
            max_heartrate=activity.max_heartrate,
            average_cadence=activity.average_cadence,
            calories=activity.calories,
            pr_count=activity.pr_count,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def distance_miles(self) -> float:
        return round(self.distance_meters / METERS_PER_MILE, 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pace_min_per_mile(self) -> float | None:
        miles = self.distance_meters / METERS_PER_MILE
        if miles <= 0 or self.moving_time_seconds <= 0:
            return None
        return round((self.moving_time_seconds / 60.0) / miles, 2)


class ActivitiesRecentResponse(BaseModel):
    activities: list[StravaActivityRead]
    synced_at: datetime | None = None


class ActivitiesSummaryResponse(BaseModel):
    period: Literal["week", "month", "year"]
    start_date: date
    end_date: date
    total_runs: int
    total_distance_miles: float
    total_moving_time_seconds: int
    average_pace_min_per_mile: float | None
    total_elevation_gain_feet: float
    total_calories: float | None
    streak_days: int
    synced_at: datetime | None = None
