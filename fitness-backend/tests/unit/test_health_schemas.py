"""Unit tests for health schema normalization."""

from datetime import date

from app.domains.health.schemas import normalize_whoop_day


def test_normalize_whoop_day_maps_sleep_recovery_strain() -> None:
    record = normalize_whoop_day(
        record_date=date(2026, 5, 20),
        cycle={
            "score": {"strain": 14.2, "kilojoule": 1880.0},
        },
        sleep={
            "sleep_performance_percentage": 85.4,
            "sleep_efficiency_percentage": 92.5,
            "total_slow_wave_sleep_time_milli": 7_200_000,
            "total_rem_sleep_time_milli": 5_400_000,
            "total_light_sleep_time_milli": 16_200_000,
        },
        recovery={
            "score": {
                "recovery_score": 78.2,
                "resting_heart_rate": 52.0,
                "hrv_rmssd_milli": 45.0,
                "spo2_percentage": 97.5,
            },
        },
    )
    assert record.sleep_score == 85
    assert record.recovery_score == 78
    assert record.strain_score == 14.2
    assert record.active_calories == int(round(1880.0 * 0.239006))


def test_normalize_whoop_day_maps_nested_sleep_score() -> None:
    record = normalize_whoop_day(
        record_date=date(2026, 5, 21),
        cycle=None,
        sleep={
            "score_state": "SCORED",
            "score": {
                "sleep_performance_percentage": 98,
                "sleep_efficiency_percentage": 91.7,
                "stage_summary": {
                    "total_slow_wave_sleep_time_milli": 6_630_370,
                    "total_rem_sleep_time_milli": 5_879_573,
                    "total_light_sleep_time_milli": 14_905_851,
                },
            },
        },
        recovery=None,
    )

    assert record.sleep_score == 98
    assert record.sleep_efficiency == 91.7
    assert record.deep_sleep_seconds == 6630
    assert record.rem_sleep_seconds == 5879
    assert record.light_sleep_seconds == 14905
    assert record.total_sleep_seconds == 27415
