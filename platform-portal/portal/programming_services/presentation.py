from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..models.exercise_library import Exercise
LIFT_FAMILIES = ("squat", "bench", "deadlift")


def taxonomy_exposure_summary(items: Iterable[Any]) -> dict[str, int]:
    """Count S/B/D prescriptions using exact Exercise Library taxonomy."""
    names = {item.exercise_name for item in items if item.exercise_name}
    taxonomy = {
        exercise.name: exercise.lift_family
        for exercise in Exercise.query.filter(
            Exercise.name.in_(names), Exercise.active.is_(True)
        ).all()
    }
    summary = {family: 0 for family in LIFT_FAMILIES}
    for item in items:
        family = taxonomy.get(item.exercise_name)
        if family in summary:
            summary[family] += 1
    return summary


def week_exposure_summary(week: Any) -> dict[str, int]:
    return taxonomy_exposure_summary(
        item for session in week.sessions for item in session.prescriptions
    )
