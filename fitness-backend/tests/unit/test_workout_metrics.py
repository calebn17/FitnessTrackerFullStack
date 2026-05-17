"""Unit tests for derived workout metrics (Phase 5)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.domains.ai import models as _ai_models  # noqa: F401
from app.domains.users import models as _users_models  # noqa: F401
from app.domains.workouts.metrics import (
    DerivedMetricsValues,
    apply_values_to_derived_metrics,
    calculate_derived_metrics_values,
    muscle_groups_for_exercise,
    normalize_exercise_name,
)
from app.domains.workouts.models import DerivedMetrics


def _set(
    *,
    exercise_name: str,
    reps: int,
    weight: float | None = None,
    rpe: float | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        exercise_name=exercise_name,
        reps=reps,
        weight=weight,
        rpe=rpe,
    )


def test_normalize_exercise_name_collapses_whitespace_and_lowercases() -> None:
    assert normalize_exercise_name("  Bench   Press  ") == "bench press"
    assert normalize_exercise_name("PULL-UP") == "pull-up"


def test_calculate_volume_sums_weight_times_reps() -> None:
    sets = [
        _set(exercise_name="Squat", reps=5, weight=225.0),
        _set(exercise_name="Squat", reps=3, weight=315.0),
    ]
    v = calculate_derived_metrics_values(sets)
    assert v.total_volume == 5 * 225.0 + 3 * 315.0
    assert v.total_sets == 2
    assert v.total_reps == 8


def test_bodyweight_null_weight_contributes_zero_volume() -> None:
    sets = [_set(exercise_name="Pull-up", reps=10, weight=None)]
    v = calculate_derived_metrics_values(sets)
    assert v.total_volume == 0.0
    assert v.total_reps == 10


def test_avg_rpe_only_when_any_set_has_rpe() -> None:
    sets = [
        _set(exercise_name="A", reps=5, weight=100.0, rpe=8.0),
        _set(exercise_name="B", reps=5, weight=100.0, rpe=None),
    ]
    v = calculate_derived_metrics_values(sets)
    assert v.avg_rpe == 8.0

    no_rpe = [_set(exercise_name="A", reps=5, weight=100.0, rpe=None)]
    assert calculate_derived_metrics_values(no_rpe).avg_rpe is None


def test_exercise_count_unique_normalized_names() -> None:
    sets = [
        _set(exercise_name="Bench Press", reps=8, weight=135.0),
        _set(exercise_name="bench  press", reps=8, weight=135.0),
        _set(exercise_name="Squat", reps=5, weight=225.0),
    ]
    v = calculate_derived_metrics_values(sets)
    assert v.exercise_count == 2


def test_muscle_groups_union_sorted_unique() -> None:
    sets = [
        _set(exercise_name="Bench Press", reps=8, weight=185.0),
        _set(exercise_name="Squat", reps=5, weight=225.0),
    ]
    v = calculate_derived_metrics_values(sets)
    assert v.muscle_groups == [
        "chest",
        "glutes",
        "hamstrings",
        "quadriceps",
        "shoulders",
        "triceps",
    ]


def test_unknown_exercise_no_muscle_groups() -> None:
    sets = [_set(exercise_name="Zorgblorb Press", reps=10, weight=50.0)]
    v = calculate_derived_metrics_values(sets)
    assert v.muscle_groups == []
    assert muscle_groups_for_exercise("Zorgblorb Press") == []


def test_empty_sets() -> None:
    v = calculate_derived_metrics_values([])
    assert v == DerivedMetricsValues(
        total_volume=0.0,
        total_sets=0,
        total_reps=0,
        avg_rpe=None,
        exercise_count=0,
        muscle_groups=[],
    )


def test_apply_values_to_derived_metrics() -> None:
    row = DerivedMetrics(workout_id=uuid.uuid4())
    vals = DerivedMetricsValues(
        total_volume=100.0,
        total_sets=2,
        total_reps=20,
        avg_rpe=7.5,
        exercise_count=1,
        muscle_groups=["back"],
    )
    apply_values_to_derived_metrics(row, vals)
    assert row.total_volume == 100.0
    assert row.total_sets == 2
    assert row.total_reps == 20
    assert row.avg_rpe == 7.5
    assert row.exercise_count == 1
    assert row.muscle_groups == ["back"]
