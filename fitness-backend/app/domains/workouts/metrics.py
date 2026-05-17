"""Derived workout metrics (Phase 5)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.domains.workouts.models import DerivedMetrics

# Normalized exercise name (lowercase, collapsed whitespace) -> muscle groups
EXERCISE_MUSCLE_MAP: dict[str, list[str]] = {
    "bench press": ["chest", "triceps", "shoulders"],
    "squat": ["quadriceps", "glutes", "hamstrings"],
    "deadlift": ["back", "hamstrings", "glutes"],
    "overhead press": ["shoulders", "triceps"],
    "barbell row": ["back", "biceps"],
    "pull-up": ["back", "biceps"],
    "pull up": ["back", "biceps"],
    "lat pulldown": ["back", "biceps"],
    "leg press": ["quadriceps", "glutes"],
    "leg curl": ["hamstrings"],
    "leg extension": ["quadriceps"],
    "bicep curl": ["biceps"],
    "tricep pushdown": ["triceps"],
    "lateral raise": ["shoulders"],
    "face pull": ["rear delts", "upper back"],
}


class ExerciseSetLike(Protocol):
    """Minimal shape needed to derive metrics (ORM ExerciseSet satisfies this)."""

    exercise_name: str
    reps: int
    weight: float | None
    rpe: float | None


def normalize_exercise_name(name: str) -> str:
    """Lowercase and collapse internal whitespace for stable matching."""
    collapsed = re.sub(r"\s+", " ", name.strip().lower())
    return collapsed


@dataclass(frozen=True, slots=True)
class DerivedMetricsValues:
    """Computed metrics fields (maps to DerivedMetrics columns).

    Excludes id, workout_id, and created_at.
    """

    total_volume: float | None
    total_sets: int | None
    total_reps: int | None
    avg_rpe: float | None
    exercise_count: int | None
    muscle_groups: list[str] | None


def muscle_groups_for_exercise(exercise_name: str) -> list[str]:
    """Return muscle groups for a known exercise, or empty list if unknown."""
    key = normalize_exercise_name(exercise_name)
    return list(EXERCISE_MUSCLE_MAP.get(key, []))


def calculate_derived_metrics_values(sets: Sequence[ExerciseSetLike]) -> DerivedMetricsValues:
    """Compute aggregate metrics from exercise sets (in-memory ORM instances or duck-typed rows)."""
    if not sets:
        return DerivedMetricsValues(
            total_volume=0.0,
            total_sets=0,
            total_reps=0,
            avg_rpe=None,
            exercise_count=0,
            muscle_groups=[],
        )

    total_sets = len(sets)
    total_reps = sum(s.reps for s in sets)

    volume_total = 0.0
    for s in sets:
        if s.weight is not None:
            volume_total += float(s.weight) * int(s.reps)

    rpe_values = [float(s.rpe) for s in sets if s.rpe is not None]
    avg_rpe: float | None
    if rpe_values:
        avg_rpe = sum(rpe_values) / len(rpe_values)
    else:
        avg_rpe = None

    unique_names = {normalize_exercise_name(s.exercise_name) for s in sets}
    exercise_count = len(unique_names)

    muscle_set: set[str] = set()
    for s in sets:
        for g in muscle_groups_for_exercise(s.exercise_name):
            muscle_set.add(g)
    muscle_groups_sorted = sorted(muscle_set) if muscle_set else []

    return DerivedMetricsValues(
        total_volume=volume_total,
        total_sets=total_sets,
        total_reps=total_reps,
        avg_rpe=avg_rpe,
        exercise_count=exercise_count,
        muscle_groups=muscle_groups_sorted if muscle_groups_sorted else [],
    )


def apply_values_to_derived_metrics(row: DerivedMetrics, values: DerivedMetricsValues) -> None:
    """Mutate an existing DerivedMetrics ORM instance in place."""
    row.total_volume = values.total_volume
    row.total_sets = values.total_sets
    row.total_reps = values.total_reps
    row.avg_rpe = values.avg_rpe
    row.exercise_count = values.exercise_count
    row.muscle_groups = values.muscle_groups
