"""Authoritative deterministic weekly powerlifting assistance planning.

The planner deliberately owns *selection, placement and prescription*.  Callers
may render or persist its result, but must not fill empty sessions locally.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Sequence

from ..models.exercise_library import Exercise


PURPOSES = frozenset({
    "quad strength", "squat positional strength", "hip extension",
    "posterior-chain hypertrophy", "upper-back stability",
    "bench pec strength", "triceps strength", "bench stability",
    "deadlift off-floor", "deadlift lockout", "hypertrophy",
    "low-fatigue technical support",
})

_NOVELTY = (
    "atlas stone", "farmer", "yoke", "tire flip", "log press", "axle",
    "prowler", "sled", "burpee", "battle rope", "box jump", "sprint",
    "bosu", "turkish get-up",
)
_COMPLEX = ("snatch", "clean and jerk", "windmill", "renegade row")
_LOWER_PURPOSES = frozenset({
    "quad strength", "squat positional strength", "hip extension",
    "posterior-chain hypertrophy", "deadlift off-floor", "deadlift lockout",
})
_HINGE_PURPOSES = frozenset({
    "hip extension", "posterior-chain hypertrophy", "deadlift off-floor",
    "deadlift lockout",
})
_BENCH_STRESS_PURPOSES = frozenset({"bench pec strength", "triceps strength"})


def _values(value: Any) -> set[str]:
    if not value:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip().casefold() for item in value if str(item).strip()}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {part.strip().casefold() for part in str(value).split(",") if part.strip()}
    return _values(parsed) if isinstance(parsed, list) else set()


def _text(exercise: Exercise) -> str:
    return " ".join(str(value or "") for value in (
        exercise.name, exercise.family, exercise.category, exercise.movement_pattern,
        exercise.swap_group, exercise.primary_muscles, exercise.technical_purposes,
    )).casefold()


@dataclass(frozen=True)
class WeeklyAccessoryCandidate:
    """An eligible catalogue row plus authoritative Athlete State metadata."""

    exercise: Exercise
    state_score: int = 0
    state_provenance: tuple[dict[str, Any], ...] = ()
    state_reasons: tuple[str, ...] = ()


def purpose_for(exercise: Exercise) -> str:
    """Map broad/legacy catalogue language into the compact PL taxonomy."""
    tags = _values(exercise.technical_purposes) | _values(exercise.compatibility_tags)
    explicit = sorted(tags & PURPOSES)
    if explicit:
        return explicit[0]
    joined = " ".join(sorted(tags)) + " " + _text(exercise)
    rules = (
        ("deadlift off-floor", ("off floor", "off-floor", "deficit deadlift")),
        ("deadlift lockout", ("lockout", "rack pull", "block pull")),
        ("squat positional strength", ("pause squat", "paused high", "tempo squat", "pin squat", "position")),
        ("quad strength", ("quad", "leg extension", "leg press", "hack squat", "split squat", "lunge")),
        ("posterior-chain hypertrophy", ("leg curl", "hamstring curl", "hamstring hypertrophy", "back extension")),
        ("hip extension", ("romanian deadlift", "rdl", "hip thrust", "good morning", "glute")),
        ("triceps strength", ("triceps", "close grip", "close-grip", "jm press")),
        ("bench pec strength", ("pec", "chest press", "dumbbell bench", "incline press")),
        ("bench stability", ("face pull", "external rotation", "serratus", "bench stability")),
        ("upper-back stability", ("row", "pulldown", "pull-up", "chin-up", "upper back", "lat ")),
        ("low-fatigue technical support", ("technique", "bracing", "plank", "dead bug", "pallof", "grip", "hold")),
    )
    for purpose, markers in rules:
        if any(marker in joined for marker in markers):
            return purpose
    return "hypertrophy"


@dataclass(frozen=True)
class WeeklyAccessoryContext:
    goal: str
    volume: str
    week_count: int
    day_types: tuple[str, ...]
    constraints: frozenset[str] = frozenset()
    observations: frozenset[str] = frozenset()
    available_equipment: frozenset[str] | None = None
    readiness_multiplier: float = 1.0
    meet_date: date | None = None
    competition_grip: str = "mixed"
    grip_work_priority: str = "none"


@dataclass(frozen=True)
class WeekPrescription:
    week: int
    sets: int
    reps: str
    rpe: float
    rest_seconds: int


@dataclass(frozen=True)
class PlannedAccessory:
    exercise: Exercise
    day_index: int
    purpose: str
    reason: str
    prescriptions: tuple[WeekPrescription, ...]
    warnings: tuple[str, ...] = ()
    state_score: int = 0
    state_provenance: tuple[dict[str, Any], ...] = ()
    state_reasons: tuple[str, ...] = ()


class WeeklyAccessoryPlanner:
    """The single automatic accessory planner used by programme generation."""

    WEEKLY_BUDGET_PER_DAY = {"low": 2, "medium": 4, "high": 6}

    def plan(
        self,
        exercises: Iterable[Exercise | WeeklyAccessoryCandidate],
        context: WeeklyAccessoryContext,
    ) -> tuple[PlannedAccessory, ...]:
        if not 1 <= len(context.day_types) <= 7:
            raise ValueError("Weekly accessory planning requires 1-7 training days.")
        candidates = [
            item if isinstance(item, WeeklyAccessoryCandidate)
            else WeeklyAccessoryCandidate(item)
            for item in exercises
        ]
        eligible = [item for item in candidates if self._eligible(item.exercise, context)]
        eligible.sort(key=lambda item: self._rank(item, context))
        remaining = max(0, round(
            self.WEEKLY_BUDGET_PER_DAY.get(context.volume, 4)
            * len(context.day_types) * max(.5, min(1.0, context.readiness_multiplier))
        ))
        selected: list[PlannedAccessory] = []
        used_groups: set[str] = set()
        purpose_counts: dict[str, int] = {}
        day_purposes: dict[int, set[str]] = {
            i: set() for i in range(len(context.day_types))
        }

        required_grip = self._required_grip_candidate(eligible, context)
        if required_grip is not None:
            row = required_grip.exercise
            purpose = purpose_for(row)
            day = self._best_day(purpose, row, context, day_purposes)
            if day >= 0:
                reason = self._grip_reason(context)
                selected.append(
                    PlannedAccessory(
                        row,
                        day,
                        purpose,
                        reason,
                        self._prescriptions(row, purpose, context),
                        state_score=required_grip.state_score,
                        state_provenance=required_grip.state_provenance,
                        state_reasons=required_grip.state_reasons,
                    )
                )
                remaining -= max(1, min(5, row.fatigue_rating or 3))
                used_groups.add(self._redundancy_group(row, purpose))
        hinge_count = press_count = row_count = 0

        for candidate in eligible:
            row = candidate.exercise
            if required_grip is not None and row.id == required_grip.exercise.id:
                continue
            cost = max(1, min(5, row.fatigue_rating or 3))
            if cost > remaining:
                continue
            purpose = purpose_for(row)
            group = self._redundancy_group(row, purpose)
            if group in used_groups or purpose in day_purposes.get(self._best_day(purpose, row, context, day_purposes), set()):
                continue
            if purpose_counts.get(purpose, 0) >= (2 if purpose in {"upper-back stability", "hypertrophy", "low-fatigue technical support"} else 1):
                continue
            if purpose in _HINGE_PURPOSES and hinge_count >= 2:
                continue
            if purpose in _BENCH_STRESS_PURPOSES and press_count >= (1 if context.day_types.count("B") >= 3 else 2):
                continue
            if purpose == "upper-back stability" and row_count >= 2:
                continue
            day = self._best_day(purpose, row, context, day_purposes)
            if day < 0:
                continue
            reason = self._reason(row, purpose, context.day_types[day], context)
            selected.append(PlannedAccessory(
                row, day, purpose, reason, self._prescriptions(row, purpose, context),
                state_score=candidate.state_score,
                state_provenance=candidate.state_provenance,
                state_reasons=candidate.state_reasons,
            ))
            remaining -= cost
            used_groups.add(group)
            purpose_counts[purpose] = purpose_counts.get(purpose, 0) + 1
            day_purposes[day].add(purpose)
            hinge_count += purpose in _HINGE_PURPOSES
            press_count += purpose in _BENCH_STRESS_PURPOSES
            row_count += purpose == "upper-back stability"
        return tuple(sorted(
            selected,
            key=lambda item: (
                item.day_index,
                0 if required_grip is not None and item.exercise.id == required_grip.exercise.id else 1,
                item.purpose,
                item.exercise.name.casefold(),
                item.exercise.id,
            ),
        ))

    @staticmethod
    def _grip_reason(context: WeeklyAccessoryContext) -> str:
        if context.competition_grip == "hook" and context.grip_work_priority == "none":
            return "hook-grip competition requirement"
        return (
            f"grip-work priority is {context.grip_work_priority}; "
            f"competition grip is {context.competition_grip}"
        )

    def _required_grip_candidate(
        self,
        exercises: list[WeeklyAccessoryCandidate],
        context: WeeklyAccessoryContext,
    ) -> WeeklyAccessoryCandidate | None:
        required = context.competition_grip == "hook" or context.grip_work_priority != "none"
        if not required:
            return None

        candidates = []
        for candidate in exercises:
            row = candidate.exercise
            if (row.category or "").casefold() != "grip":
                continue

            text = _text(row)
            if "farmer" in text or "carry" in text:
                continue

            hook_specific = "hook grip" in text or "hook-grip" in text
            candidates.append(
                (
                    -int(context.competition_grip == "hook" and hook_specific),
                    -candidate.state_score,
                    -row.coach_priority,
                    max(1, min(5, row.fatigue_rating or 3)),
                    row.name.casefold(),
                    row.id,
                    candidate,
                )
            )

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[:-1])
        return candidates[0][-1]

    def _eligible(self, row: Exercise, context: WeeklyAccessoryContext) -> bool:
        # auto_select is intentionally a hard gate. Pins are handled by the caller.
        if not row.active or not row.accessory_suitable or not row.auto_select:
            return False
        text = _text(row)
        if (row.category or "").casefold() in {"strongman", "specialty", "conditioning", "cardio"}:
            return False
        if any(marker in text for marker in (*_NOVELTY, *_COMPLEX)):
            return False
        phases = _values(row.training_phases)
        if phases and not ({context.goal.casefold(), "all"} & phases):
            return False
        relevance = _values(row.lift_relevance)
        scheduled = {
            {"S": "squat", "B": "bench", "D": "deadlift"}[code]
            for day in context.day_types for code in day
        }
        if relevance and "all" not in relevance and not relevance & scheduled:
            return False
        if (row.category or "").casefold() == "grip":
            grip_required = context.competition_grip == "hook" or context.grip_work_priority != "none"
            if not grip_required:
                return False
        if context.constraints & _values(row.constraint_tags):
            return False
        if context.available_equipment is not None:
            options = _values(row.equipment_options)
            if row.equipment:
                options.add(row.equipment.casefold())
            if options and not options & context.available_equipment:
                return False
        return True

    def _rank(
        self, candidate: WeeklyAccessoryCandidate, context: WeeklyAccessoryContext
    ) -> tuple[Any, ...]:
        row = candidate.exercise
        purpose = purpose_for(row)
        candidate_signals = _values(row.technical_purposes) | _values(row.compatibility_tags) | {purpose}
        candidate_text = _text(row) + " " + " ".join(candidate_signals)
        observation_match = bool(context.observations & candidate_signals) or any(
            signal in candidate_text or purpose in signal
            for signal in context.observations
        )
        relevance = _values(row.lift_relevance)
        scheduled = {"squat" if "S" in d else "" for d in context.day_types} | {"bench" if "B" in d else "" for d in context.day_types} | {"deadlift" if "D" in d else "" for d in context.day_types}
        relevant = not relevance or "all" in relevance or bool(relevance & scheduled)
        grip_match = (
            (context.competition_grip == "hook" or context.grip_work_priority != "none")
            and (row.category or "").casefold() == "grip"
        )
        return (-int(grip_match), -candidate.state_score, -int(observation_match), -int(relevant), -row.coach_priority,
                max(1, min(5, row.fatigue_rating or 3)), row.name.casefold(), row.id)

    @staticmethod
    def _redundancy_group(row: Exercise, purpose: str) -> str:
        group = (row.swap_group or row.variation_of or row.movement_pattern or "").strip().casefold()
        text = _text(row)
        if "row" in text:
            return "row"
        if any(x in text for x in ("press", "bench", "dip")):
            return "press"
        if purpose in _HINGE_PURPOSES:
            return group or "hinge"
        return group or f"purpose:{purpose}"

    def _best_day(self, purpose: str, row: Exercise, context: WeeklyAccessoryContext,
                  occupied: dict[int, set[str]]) -> int:
        relevance = _values(row.lift_relevance)
        desired = (
            "D" if purpose in _HINGE_PURPOSES
            else "S" if purpose in {"quad strength", "squat positional strength"}
            else "B" if purpose in _BENCH_STRESS_PURPOSES | {"bench stability", "upper-back stability"}
            else ""
        )
        choices = []
        n = len(context.day_types)
        for index, day_type in enumerate(context.day_types):
            if purpose in occupied[index] or len(occupied[index]) >= 3:
                continue
            next_day = context.day_types[(index + 1) % n] if n > 1 else ""
            collision = 0
            if purpose in _LOWER_PURPOSES and any(code in next_day for code in "SD"):
                collision += 6
            if purpose in _BENCH_STRESS_PURPOSES and "B" in next_day:
                collision += 5
            match = bool(desired and desired in day_type)
            metadata_match = not relevance or "all" in relevance or any(
                {"S": "squat", "B": "bench", "D": "deadlift"}[code] in relevance
                for code in day_type
            )
            # Put stressful work after its relevant exposure; spread all work.
            choices.append((collision, -int(match), -int(metadata_match), len(occupied[index]), index))
        return min(choices)[-1] if choices else -1

    @staticmethod
    def _reason(row: Exercise, purpose: str, day_type: str,
                context: WeeklyAccessoryContext) -> str:
        observation = context.observations & (
            _values(row.technical_purposes) | _values(row.compatibility_tags) | {purpose}
        )
        suffix = f"; addresses {sorted(observation)[0]}" if observation else ""
        return f"{purpose.capitalize()} after {day_type} exposure with fatigue cost {max(1, min(5, row.fatigue_rating or 3))}/5{suffix}."

    @staticmethod
    def _prescriptions(row: Exercise, purpose: str,
                       context: WeeklyAccessoryContext) -> tuple[WeekPrescription, ...]:
        fatigue = max(1, min(5, row.fatigue_rating or 3))
        compound = fatigue >= 4 or purpose in {
            "quad strength", "squat positional strength", "hip extension",
            "bench pec strength", "deadlift off-floor", "deadlift lockout",
        }
        base_sets = row.default_sets or (3 if compound else 2)
        reps = row.default_reps or ("5-8" if compound else "10-15")
        base_rpe = row.default_rpe or (7.0 if compound else 8.0)
        rest = row.default_rest_seconds or (180 if compound else 90)
        result = []
        for week in range(1, context.week_count + 1):
            progress = 0.5 * min(2, week - 1)
            sets = base_sets
            rpe = min(8.5, base_rpe + progress)
            # A normal final deload and all meet-proximal peaking weeks reduce
            # assistance. This is persisted, not merely described in preview.
            days_to_meet = (
                (context.meet_date - date.today()).days - ((week - 1) * 7)
                if context.meet_date is not None else None
            )
            meet_proximal = days_to_meet is not None and days_to_meet <= 14
            taper = (context.goal == "peaking" or meet_proximal) and (
                context.week_count == 1 or week >= max(1, context.week_count - 1)
            )
            if taper or (context.week_count > 1 and week == context.week_count and context.goal != "hypertrophy"):
                sets = max(1, base_sets - (2 if fatigue >= 4 else 1))
                rpe = min(rpe, 7.0)
            result.append(WeekPrescription(week, sets, reps, round(rpe * 2) / 2, rest))
        return tuple(result)
