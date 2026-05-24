"""Unit tests for activity schema computed fields."""

from datetime import UTC, datetime
from uuid import uuid4

from app.domains.activities.schemas import METERS_PER_MILE, StravaActivityRead


def test_strava_activity_read_computed_distance_and_pace() -> None:
    miles = 5.0
    meters = miles * METERS_PER_MILE
    read = StravaActivityRead(
        id=uuid4(),
        strava_id=1,
        sport_type="Run",
        start_date_local=datetime.now(UTC),
        distance_meters=meters,
        moving_time_seconds=2400,
        elapsed_time_seconds=2520,
        average_speed_mps=3.35,
        total_elevation_gain_meters=45.0,
    )
    assert read.distance_miles == miles
    assert read.pace_min_per_mile == 8.0
