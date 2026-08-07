"""Explainable candidate filtering for a future coach-facing swap workflow.

This module does not alter programming and is deliberately independent of the
Block Factory. A caller must still present candidates to a coach for a choice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from ..models.exercise_library import Exercise


@dataclass(frozen=True)
class SwapCandidate:
    exercise: Exercise
    reasons: tuple[str, ...]


def compatible_swaps(
    source: Exercise,
    exercises: Iterable[Exercise],
    *,
    available_equipment: set[str] | None = None,
    excluded_constraint_tags: set[str] | None = None,
) -> list[SwapCandidate]:
    """Return deterministic candidates that preserve the source swap group.

    Equipment values are exact catalogue options, not inferred facilities.
    Constraint tags describe setup properties and must not be treated as a
    diagnosis or a claim that an exercise is suitable for an injury.
    """

    if not source.swap_group:
        return []
    excluded_constraint_tags = excluded_constraint_tags or set()
    candidates: list[SwapCandidate] = []
    for exercise in exercises:
        if exercise.id == source.id or not exercise.active:
            continue
        if exercise.swap_group != source.swap_group:
            continue
        constraints = set(_json_list(exercise.constraint_tags))
        if constraints.intersection(excluded_constraint_tags):
            continue
        equipment = set(_json_list(exercise.equipment_options))
        if available_equipment is not None and not equipment.intersection(available_equipment):
            continue
        reasons = [f"same swap group: {source.swap_group}"]
        if exercise.specificity == source.specificity:
            reasons.append(f"same specificity: {source.specificity}")
        if exercise.fatigue_rating == source.fatigue_rating:
            reasons.append(f"same fatigue rating: {source.fatigue_rating}/5")
        if equipment:
            reasons.append("equipment option available")
        candidates.append(SwapCandidate(exercise, tuple(reasons)))

    # Ordering is intentionally inspectable: specificity, fatigue distance,
    # then name. It is not a hidden suitability score.
    return sorted(
        candidates,
        key=lambda item: (
            item.exercise.specificity != source.specificity,
            abs(item.exercise.fatigue_rating - source.fatigue_rating),
            item.exercise.name.casefold(),
        ),
    )


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else []
