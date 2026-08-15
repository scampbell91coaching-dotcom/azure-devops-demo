"""Deterministic, explainable accessory candidate selection."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class AccessoryRankingContext:
    """Explicit, caller-owned facts used by the deterministic ranking policy."""

    block_type: str
    goal: str
    session_lift_exposure: frozenset[str]
    fatigue_budget: int
    athlete_constraint_tags: frozenset[str] = field(default_factory=frozenset)
    technical_observation_tags: frozenset[str] = field(default_factory=frozenset)
    available_equipment: frozenset[str] | None = None
    pinned_exercise_ids: tuple[int, ...] = ()
    recent_exercise_ids: frozenset[int] = field(default_factory=frozenset)
    current_exercise_ids: frozenset[int] = field(default_factory=frozenset)


@dataclass(frozen=True)
class RankedAccessoryCandidate:
    exercise: Exercise
    status: str
    fatigue_cost: int
    rule_ids: tuple[str, ...]
    evidence: tuple[str, ...]
    reason: str


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

    def ranked_candidates(
        self, context: AccessoryRankingContext
    ) -> list[RankedAccessoryCandidate]:
        """Rank and select candidates while retaining every exclusion decision.

        Pins are returned first, in coach order, and do not consume or obey the
        automatic fatigue budget. Automatic rows are selected greedily by an
        explainable score, then fatigue and stable catalogue identity. No count
        target or ceiling is applied.
        """
        block_type = context.block_type.strip().casefold()
        goal = context.goal.strip().casefold()
        lifts = {value.casefold() for value in context.session_lift_exposure}
        constraints = {value.casefold() for value in context.athlete_constraint_tags}
        observations = {value.casefold() for value in context.technical_observation_tags}
        equipment = (
            {value.casefold() for value in context.available_equipment}
            if context.available_equipment is not None else None
        )
        pin_order: dict[int, int] = {}
        for exercise_id in context.pinned_exercise_ids:
            pin_order.setdefault(exercise_id, len(pin_order))
        scored: list[tuple[int, int, str, int, Exercise, list[str], list[str]]] = []
        excluded: list[RankedAccessoryCandidate] = []

        for exercise in self.repository.selection_candidates(include_ids=set(pin_order)):
            cost = max(1, min(5, exercise.fatigue_rating or 3))
            rules: list[str] = []
            evidence: list[str] = []
            is_pinned = exercise.id in pin_order
            if is_pinned:
                rules.append("PIN_AUTHORITATIVE")
                evidence.append(f"coach pin position {pin_order[exercise.id] + 1}")
                scored.append((1_000_000_000 - pin_order[exercise.id], cost, exercise.name.casefold(), exercise.id, exercise, rules, evidence))
                continue

            failures: list[tuple[str, str]] = []
            if not exercise.active:
                failures.append(("META_INACTIVE", "catalogue row is inactive"))
            if not exercise.accessory_suitable:
                failures.append(("META_NOT_ACCESSORY_SUITABLE", "not marked accessory suitable"))
            if not exercise.auto_select:
                failures.append(("META_NOT_ENABLED", "coach has not enabled automatic selection"))

            phases = metadata_values(exercise.training_phases)
            relevance = metadata_values(exercise.lift_relevance)
            constraint_tags = metadata_values(exercise.constraint_tags)
            purposes = metadata_values(exercise.technical_purposes)
            options = metadata_values(exercise.equipment_options)
            if exercise.equipment:
                options.add(exercise.equipment.strip().casefold())
            accepted_phases = {block_type, goal, "all"}
            if phases and phases.isdisjoint(accepted_phases):
                failures.append(("CONTEXT_BLOCK_GOAL_MISMATCH", f"phases {sorted(phases)} do not match block type/goal"))
            matched_lifts = lifts.intersection(relevance)
            if relevance and "all" not in relevance and not matched_lifts:
                failures.append(("CONTEXT_LIFT_EXPOSURE_MISMATCH", f"lift relevance {sorted(relevance)} does not match session exposure"))
            matched_constraints = constraints.intersection(constraint_tags)
            if matched_constraints:
                failures.append(("ATHLETE_CONSTRAINT_EXCLUDED", f"athlete constraint matched {sorted(matched_constraints)}"))
            if equipment is not None and options and equipment.isdisjoint(options):
                failures.append(("EQUIPMENT_UNAVAILABLE", f"requires one of {sorted(options)}"))
            if exercise.id in context.current_exercise_ids:
                failures.append(("STATE_ALREADY_CURRENT", "already present in current programming state"))
            elif exercise.id in context.recent_exercise_ids:
                failures.append(("STATE_RECENTLY_USED", "recently used; prefer a non-recent candidate"))

            if failures:
                excluded.append(RankedAccessoryCandidate(
                    exercise, "excluded", cost,
                    tuple(rule for rule, _ in failures),
                    tuple(detail for _, detail in failures),
                    "; ".join(detail for _, detail in failures),
                ))
                continue

            score = exercise.coach_priority * 100
            rules.extend(("META_ELIGIBLE", "FATIGUE_COST"))
            evidence.extend(("active, accessory suitable, and coach enabled", f"fatigue cost {cost}"))
            if matched_lifts or "all" in relevance:
                score += 30
                rules.append("CONTEXT_LIFT_EXPOSURE_MATCH")
                evidence.append(f"matches session lift exposure {sorted(matched_lifts) or ['all']}")
            if phases.intersection(accepted_phases):
                score += 20
                rules.append("CONTEXT_BLOCK_GOAL_MATCH")
                evidence.append(f"matches {block_type} block / {goal} goal")
            matched_observations = observations.intersection(purposes | metadata_values(exercise.compatibility_tags))
            if matched_observations:
                score += 40
                rules.append("ATHLETE_TECHNICAL_OBSERVATION_MATCH")
                evidence.append(f"addresses technical observation {sorted(matched_observations)}")
            if equipment is not None and options:
                rules.append("EQUIPMENT_AVAILABLE")
                evidence.append(f"available equipment match {sorted(equipment.intersection(options))}")
            scored.append((score, cost, exercise.name.casefold(), exercise.id, exercise, rules, evidence))

        scored.sort(key=lambda item: (-item[0], item[1], item[2], item[3]))
        remaining = max(0, context.fatigue_budget)
        ranked: list[RankedAccessoryCandidate] = []
        for _, cost, _, _, exercise, rules, evidence in scored:
            if exercise.id in pin_order:
                ranked.append(RankedAccessoryCandidate(exercise, "selected", cost, tuple(rules), tuple(evidence), "Coach-pinned choice is authoritative."))
            elif cost <= remaining:
                remaining -= cost
                selected_evidence = (*evidence, f"fits remaining fatigue budget; {remaining} units remain")
                ranked.append(RankedAccessoryCandidate(exercise, "selected", cost, (*rules, "FATIGUE_BUDGET_SELECTED"), selected_evidence, "; ".join(selected_evidence)))
            else:
                budget_evidence = (*evidence, f"fatigue cost {cost} exceeds remaining budget {remaining}")
                ranked.append(RankedAccessoryCandidate(exercise, "excluded", cost, (*rules, "FATIGUE_BUDGET_EXCEEDED"), budget_evidence, "; ".join(budget_evidence)))
        excluded.sort(key=lambda item: (item.exercise.name.casefold(), item.exercise.id))
        return ranked + excluded

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
        # Hook grip itself is an explicit competition requirement. It must make
        # hook-specific practice eligible even when generic grip work is not a
        # priority; every other competition grip retains the opt-out.
        if priority == "none" and competition_grip != "hook":
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
                (
                    "hook-grip competition requirement"
                    if priority == "none"
                    else f"grip-work priority is {priority}"
                ),
                f"matched {family}",
                f"competition grip is {competition_grip}",
            ))
            if strap_usage != "none":
                reasons.append(
                    f"training strap usage is {strap_usage}; unstrapped exposure is programmed separately"
                )
            results.append(AccessorySuggestion(exercise, tuple(reasons)))
        return results
