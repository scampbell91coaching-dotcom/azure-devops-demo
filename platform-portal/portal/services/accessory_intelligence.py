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
    # These are fatigue-unit budgets, not accessory-count limits.  The catalogue
    # default fatigue rating is 3, preserving the established 1/2/3 output for
    # legacy rows while allowing more low-fatigue work when metadata justifies it.
    VOLUME_FATIGUE_BUDGETS = {"low": 3, "medium": 6, "high": 9}
    GRIP_PURPOSES = {
        "grip", "grip_strength", "deadlift_grip", "hook_grip",
        "static_hold", "double_overhand", "no_strap",
    }

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

        ``auto_select`` is a preference signal: preferred eligible rows rank
        before fallback rows, but its absence never makes an otherwise eligible
        catalogue empty. Empty phase/relevance metadata means unrestricted.
        Constraint tags are exact tags; they are not athlete-state diagnoses.
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

            reasons = [
                "preferred for automatic selection"
                if exercise.auto_select
                else "eligible accessory fallback"
            ]
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

    def select_for_volume(
        self,
        candidates: list[AccessorySuggestion],
        *,
        volume: str,
    ) -> list[AccessorySuggestion]:
        """Fill a deterministic fatigue budget without imposing a count ceiling.

        Candidates retain repository priority order. A row which does not fit the
        remaining budget is skipped so later, lower-fatigue eligible work can
        still be selected. Ratings are clamped to the catalogue's documented
        1-5 scale; this also handles malformed legacy values conservatively.
        """
        budget = self.VOLUME_FATIGUE_BUDGETS.get(
            volume, self.VOLUME_FATIGUE_BUDGETS["medium"]
        )
        remaining = budget
        selected: list[AccessorySuggestion] = []
        for suggestion in candidates:
            fatigue_cost = max(1, min(5, suggestion.exercise.fatigue_rating or 3))
            if fatigue_cost > remaining:
                continue
            reasons = (
                *suggestion.reasons,
                f"fits {volume} fatigue budget ({fatigue_cost}/{budget})",
            )
            selected.append(AccessorySuggestion(suggestion.exercise, reasons))
            remaining -= fatigue_cost
            if remaining == 0:
                break
        return selected

    def grip_candidates(
        self,
        *,
        phase: str,
        competition_grip: str,
        strap_usage: str,
        priority: str,
        exclude_ids: set[int] | None = None,
    ) -> list[AccessorySuggestion]:
        """Return a conservative deadlift-grip shortlist.

        Catalogue metadata is preferred. A small set of recognisable exercise
        families is supported for legacy rows; loaded carries are deliberately
        excluded so grip work does not collapse into farmer-carry suggestions.
        """
        if priority == "none":
            return []
        results: list[AccessorySuggestion] = []
        for suggestion in self.candidates(
            phase=phase,
            lift_families={"deadlift"},
            exclude_ids=exclude_ids,
        ):
            exercise = suggestion.exercise
            purposes = metadata_values(exercise.technical_purposes)
            tags = purposes | metadata_values(exercise.compatibility_tags)
            name = exercise.name.casefold().replace("-", " ")
            if "farmer" in name or "carry" in name:
                continue
            family = None
            if tags.intersection(self.GRIP_PURPOSES):
                family = "catalogue grip metadata"
            elif "hook grip" in name:
                family = "hook-grip practice/tolerance"
            elif "double overhand" in name:
                family = "double-overhand hold"
            elif "bar hold" in name or "static hold" in name or "grip hold" in name:
                family = "static bar hold"
            elif "no strap" in name and "deadlift" in name:
                family = "controlled no-strap deadlift exposure"
            if family is None:
                continue
            reasons = list(suggestion.reasons)
            reasons.extend((
                f"grip-work priority is {priority}",
                f"matched {family}",
                f"competition grip is {competition_grip}",
            ))
            if strap_usage != "none":
                reasons.append(
                    f"training strap usage is {strap_usage}; unstrapped exposure is programmed separately"
                )
            results.append(AccessorySuggestion(exercise, tuple(reasons)))
        return results
