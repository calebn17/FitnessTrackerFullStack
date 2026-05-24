"""Pydantic schemas for health endpoints."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.domains.health.models import DailyHealthRecord

from pydantic import BaseModel, ConfigDict

KILOJOULE_TO_KCAL = 0.239006


class SleepMetrics(BaseModel):
    score: int | None = None
    total_sleep_seconds: int | None = None
    deep_sleep_seconds: int | None = None
    rem_sleep_seconds: int | None = None
    light_sleep_seconds: int | None = None
    efficiency: float | None = None


class RecoveryMetrics(BaseModel):
    score: int | None = None
    resting_heart_rate: float | None = None
    hrv: float | None = None
    spo2: float | None = None


class StrainMetrics(BaseModel):
    score: float | None = None
    active_calories: int | None = None
    total_calories: int | None = None
    steps: int | None = None


class DailyHealthRead(BaseModel):
    date: date
    provider: str
    sleep: SleepMetrics
    recovery: RecoveryMetrics
    strain: StrainMetrics
    synced_at: datetime | None = None

    @classmethod
    def from_record(
        cls,
        row: DailyHealthRecord,
        *,
        synced_at: datetime | None = None,
    ) -> DailyHealthRead:
        record = row
        return cls(
            date=record.date,
            provider=record.provider,
            sleep=SleepMetrics(
                score=record.sleep_score,
                total_sleep_seconds=record.total_sleep_seconds,
                deep_sleep_seconds=record.deep_sleep_seconds,
                rem_sleep_seconds=record.rem_sleep_seconds,
                light_sleep_seconds=record.light_sleep_seconds,
                efficiency=record.sleep_efficiency,
            ),
            recovery=RecoveryMetrics(
                score=record.recovery_score,
                resting_heart_rate=record.resting_heart_rate,
                hrv=record.hrv,
                spo2=record.spo2,
            ),
            strain=StrainMetrics(
                score=record.strain_score,
                active_calories=record.active_calories,
                total_calories=record.total_calories,
                steps=record.steps,
            ),
            synced_at=synced_at,
        )


class HealthTodayResponse(DailyHealthRead):
    pass


class HealthRecentResponse(BaseModel):
    records: list[DailyHealthRead]
    synced_at: datetime | None = None


class HealthSummaryResponse(BaseModel):
    period_days: int
    actual_days_with_data: int
    provider: str
    avg_sleep_score: float | None = None
    avg_total_sleep_hours: float | None = None
    avg_recovery_score: float | None = None
    avg_resting_heart_rate: float | None = None
    avg_hrv: float | None = None
    avg_strain_score: float | None = None
    avg_active_calories: float | None = None
    synced_at: datetime | None = None


class HealthRecordUpsert(BaseModel):
    """Normalized daily health fields for persistence."""

    model_config = ConfigDict(extra="ignore")

    date: date
    provider: str = "whoop"
    sleep_score: int | None = None
    total_sleep_seconds: int | None = None
    deep_sleep_seconds: int | None = None
    rem_sleep_seconds: int | None = None
    light_sleep_seconds: int | None = None
    sleep_efficiency: float | None = None
    recovery_score: int | None = None
    resting_heart_rate: float | None = None
    hrv: float | None = None
    spo2: float | None = None
    strain_score: float | None = None
    active_calories: int | None = None
    total_calories: int | None = None
    steps: int | None = None


def normalize_whoop_day(
    *,
    record_date: date,
    cycle: dict[str, Any] | None,
    sleep: dict[str, Any] | None,
    recovery: dict[str, Any] | None,
) -> HealthRecordUpsert:
    """Map Whoop cycle/sleep/recovery payloads into common schema."""
    sleep_score: int | None = None
    total_sleep_seconds: int | None = None
    deep_sleep_seconds: int | None = None
    rem_sleep_seconds: int | None = None
    light_sleep_seconds: int | None = None
    sleep_efficiency: float | None = None
    if sleep:
        score_obj = sleep.get("score")
        sleep_score_obj = score_obj if isinstance(score_obj, dict) else {}
        stage_summary_obj = sleep_score_obj.get("stage_summary")
        stage_summary = stage_summary_obj if isinstance(stage_summary_obj, dict) else {}

        def first_present(key: str, *, stage: bool = False) -> Any:
            nested = stage_summary if stage else sleep_score_obj
            value = nested.get(key)
            if value is not None:
                return value
            return sleep.get(key)

        perf = first_present("sleep_performance_percentage")
        if perf is not None:
            sleep_score = int(round(float(perf)))
        sleep_efficiency_raw = first_present("sleep_efficiency_percentage")
        if sleep_efficiency_raw is not None:
            sleep_efficiency = float(sleep_efficiency_raw)
        deep_ms = first_present("total_slow_wave_sleep_time_milli", stage=True)
        rem_ms = first_present("total_rem_sleep_time_milli", stage=True)
        light_ms = first_present("total_light_sleep_time_milli", stage=True)
        awake_ms = first_present("total_awake_time_milli", stage=True) or 0
        stage_total = sum(
            int(x) for x in (deep_ms, rem_ms, light_ms) if x is not None
        )
        if stage_total > 0:
            total_sleep_seconds = stage_total // 1000
        if deep_ms is not None:
            deep_sleep_seconds = int(deep_ms) // 1000
        if rem_ms is not None:
            rem_sleep_seconds = int(rem_ms) // 1000
        if light_ms is not None:
            light_sleep_seconds = int(light_ms) // 1000
        total_in_bed_ms = first_present("total_in_bed_time_milli", stage=True)
        if total_sleep_seconds is None and total_in_bed_ms:
            total_sleep_seconds = max(
                0,
                int(total_in_bed_ms) // 1000 - int(awake_ms) // 1000,
            )

    recovery_score: int | None = None
    resting_heart_rate: float | None = None
    hrv: float | None = None
    spo2: float | None = None
    if recovery:
        score_obj = recovery.get("score")
        if isinstance(score_obj, dict):
            raw_recovery = score_obj.get("recovery_score")
            if raw_recovery is not None:
                recovery_score = int(round(float(raw_recovery)))
            rhr = score_obj.get("resting_heart_rate")
            if rhr is not None:
                resting_heart_rate = float(rhr)
            hrv_raw = score_obj.get("hrv_rmssd_milli")
            if hrv_raw is not None:
                hrv = float(hrv_raw)
            spo2_raw = score_obj.get("spo2_percentage")
            if spo2_raw is not None:
                spo2 = float(spo2_raw)

    strain_score: float | None = None
    active_calories: int | None = None
    if cycle:
        cycle_score = cycle.get("score")
        if isinstance(cycle_score, dict):
            strain_raw = cycle_score.get("strain")
            if strain_raw is not None:
                strain_score = float(strain_raw)
            kj = cycle_score.get("kilojoule")
            if kj is not None:
                active_calories = int(round(float(kj) * KILOJOULE_TO_KCAL))

    return HealthRecordUpsert(
        date=record_date,
        provider="whoop",
        sleep_score=sleep_score,
        total_sleep_seconds=total_sleep_seconds,
        deep_sleep_seconds=deep_sleep_seconds,
        rem_sleep_seconds=rem_sleep_seconds,
        light_sleep_seconds=light_sleep_seconds,
        sleep_efficiency=sleep_efficiency,
        recovery_score=recovery_score,
        resting_heart_rate=resting_heart_rate,
        hrv=hrv,
        spo2=spo2,
        strain_score=strain_score,
        active_calories=active_calories,
    )
