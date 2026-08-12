"""Deterministic, explainable accessory candidate selection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from ..models.exercise_library import Exercise
from ..repositories.accessory_repository import AccessoryRepository
from .accessory_state_rules import AssistanceStateContext, active_assistance_rules


@dataclass(frozen=True)
class AccessorySuggestion:
    exercise: Exercise
    reasons: tuple[str, ...]
    state_score: int = 0
    provenance: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ExcludedAccessory:
    exercise: Exercise
    reasons: tuple[str, ...]
    provenance: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class AccessoryEvaluation:
    candidates: tuple[AccessorySuggestion, ...]
    excluded: tuple[ExcludedAccessory, ...]


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
        athlete_id: int | None = None,
        session_tags: set[str] | None = None,
        as_of: date | None = None,
    ) -> list[AccessorySuggestion]:
        """Return eligible records in an inspectable coach-priority order.

        ``auto_select`` is a preference signal: preferred eligible rows rank
        before fallback rows, but its absence never makes an otherwise eligible
        catalogue empty. Empty phase/relevance metadata means unrestricted.
        Constraint tags are exact tags; they are not athlete-state diagnoses.
        """
        return list(self.evaluate_candidates(
            phase=phase,
            lift_families=lift_families,
            required_compatibility_tags=required_compatibility_tags,
            excluded_constraint_tags=excluded_constraint_tags,
            exclude_ids=exclude_ids,
            athlete_id=athlete_id,
            session_tags=session_tags,
            as_of=as_of,
        ).candidates)

    def evaluate_candidates(
        self,
        *,
        phase: str,
        lift_families: set[str],
        required_compatibility_tags: set[str] | None = None,
        excluded_constraint_tags: set[str] | None = None,
        exclude_ids: set[int] | None = None,
        athlete_id: int | None = None,
        session_tags: set[str] | None = None,
        as_of: date | None = None,
    ) -> AccessoryEvaluation:
        """Evaluate eligible and excluded candidates with state provenance."""
        phase = phase.casefold()
        lift_families = {item.casefold() for item in lift_families}
        required = {item.casefold() for item in required_compatibility_tags or set()}
        excluded_tags = {item.casefold() for item in excluded_constraint_tags or set()}
        excluded_ids = exclude_ids or set()
        state_rules = active_assistance_rules(AssistanceStateContext(
            athlete_id=athlete_id,
            phase=phase,
            lift_families=frozenset(lift_families),
            session_tags=frozenset(item.casefold() for item in session_tags or set()),
            as_of=as_of,
        )) if athlete_id is not None else ()
        results: list[AccessorySuggestion] = []
        state_excluded: list[ExcludedAccessory] = []

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
            if excluded_tags.intersection(constraints):
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
            candidate_tags = constraints | compatibility | metadata_values(exercise.technical_purposes)
            matched_rules = [rule for rule in state_rules if rule.candidate_tags.intersection(candidate_tags)]
            hard_rules = [rule for rule in matched_rules if rule.effect == "exclude"]
            if hard_rules:
                state_excluded.append(ExcludedAccessory(
                    exercise,
                    tuple(f"excluded: {rule.reason}" for rule in hard_rules),
                    tuple(rule.provenance for rule in hard_rules),
                ))
                continue
            score = sum(
                rule.weight if rule.effect == "preference" else -rule.weight
                for rule in matched_rules
            )
            for rule in matched_rules:
                signed_weight = rule.weight if rule.effect == "preference" else -rule.weight
                reasons.append(f"{rule.effect}: {rule.reason} ({signed_weight:+d})")
            results.append(AccessorySuggestion(
                exercise, tuple(reasons), score,
                tuple(rule.provenance for rule in matched_rules),
            ))

        results.sort(key=lambda item: (
            -item.state_score,
            -item.exercise.coach_priority,
            item.exercise.fatigue_rating,
            item.exercise.name,
        ))
        return AccessoryEvaluation(tuple(results), tuple(state_excluded))

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
            selected.append(AccessorySuggestion(
                suggestion.exercise, reasons, suggestion.state_score, suggestion.provenance
            ))
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
        athlete_id: int | None = None,
        session_tags: set[str] | None = None,
        as_of: date | None = None,
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
            athlete_id=athlete_id,
            session_tags=session_tags,
            as_of=as_of,
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
