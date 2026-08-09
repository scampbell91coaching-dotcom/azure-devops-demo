"""Deterministic, explainable accessory candidate selection."""

from __future__ import annotations

import json
from dataclasses import dataclass

from ..models.exercise_library import Exercise
from ..repositories.accessory_repository import AccessoryRepository


@dataclass(frozen=True)
class AccessorySuggestion:
    exercise: Exercise
    reasons: tuple[str, ...]


def metadata_values(value: str | None) -> set[str]:
    """Read the catalogue's JSON-list representation without guessing values."""
    if not value:
        return set()
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return set()
    if not isinstance(parsed, list):
        return set()
    return {str(item).strip().casefold() for item in parsed if str(item).strip()}


class AccessoryIntelligence:
    def __init__(self, repository: AccessoryRepository | None = None) -> None:
        self.repository = repository or AccessoryRepository()

    def candidates(
        self,
        *,
        phase: str,
        lift_families: set[str],
        required_compatibility_tags: set[str] | None = None,
        excluded_constraint_tags: set[str] | None = None,
        exclude_ids: set[int] | None = None,
    ) -> list[AccessorySuggestion]:
        """Return eligible records in an inspectable coach-priority order.

        Empty phase/relevance metadata means "unrestricted" only after the coach
        has explicitly enabled ``auto_select``. Constraint tags are exact tags;
        they are not athlete-state or injury diagnoses.
        """
        phase = phase.casefold()
        lift_families = {item.casefold() for item in lift_families}
        required = {item.casefold() for item in required_compatibility_tags or set()}
        excluded = {item.casefold() for item in excluded_constraint_tags or set()}
        excluded_ids = exclude_ids or set()
        results: list[AccessorySuggestion] = []

        for exercise in self.repository.automatic_candidates():
            if exercise.id in excluded_ids:
                continue
            phases = metadata_values(exercise.training_phases)
            relevance = metadata_values(exercise.lift_relevance)
            compatibility = metadata_values(exercise.compatibility_tags)
            constraints = metadata_values(exercise.constraint_tags)
            if phases and phase not in phases and "all" not in phases:
                continue
            matched_lifts = sorted(lift_families.intersection(relevance))
            if relevance and not matched_lifts and "all" not in relevance:
                continue
            if required and not required.issubset(compatibility):
                continue
            if excluded.intersection(constraints):
                continue

            reasons = ["coach enabled automatic selection"]
            if matched_lifts:
                reasons.append(f"relevant to {', '.join(matched_lifts)}")
            elif "all" in relevance:
                reasons.append("relevant to all competition lifts")
            if phase in phases:
                reasons.append(f"suitable for {phase} phase")
            elif "all" in phases:
                reasons.append("suitable for all training phases")
            reasons.append(f"coach priority {exercise.coach_priority}")
            reasons.append(f"fatigue cost {exercise.fatigue_rating}/5")
            results.append(AccessorySuggestion(exercise, tuple(reasons)))

        return results
