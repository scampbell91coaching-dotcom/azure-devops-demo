"""Purpose-led, deterministic weekly accessory planning.

This module is the sole owner of automatic accessory purpose, selection,
placement, ordering and initial dose.  It intentionally refuses to guess when
the catalogue does not contain decision-grade semantics.
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
    "deadlift off-floor", "deadlift lockout", "general hypertrophy",
    "low-fatigue technical support", "coordination/control",
})

_PATTERN_PURPOSE = {
    # Conservative mappings from structured catalogue fields only.  Exercise
    # names are display data, never automatic-selection evidence.
    "knee_extension": "quad strength", "squat": "squat positional strength",
    "hip_extension": "hip extension", "knee_flexion": "posterior-chain hypertrophy",
    "horizontal_pull": "upper-back stability", "vertical_pull": "upper-back stability",
    "horizontal_press": "bench pec strength", "elbow_extension": "triceps strength",
    "scapular_control": "bench stability", "deadlift_off_floor": "deadlift off-floor",
    "deadlift_lockout": "deadlift lockout", "trunk": "low-fatigue technical support",
    "elbow_flexion": "general hypertrophy", "single_leg_hinge": "coordination/control",
    "hinge": "hip extension", "grip_a": "low-fatigue technical support",
    "grip_b": "low-fatigue technical support",
}
_LOWER = frozenset({"quad strength", "squat positional strength", "hip extension",
                    "posterior-chain hypertrophy", "deadlift off-floor", "deadlift lockout",
                    "coordination/control"})
_HINGE = frozenset({"hip extension", "posterior-chain hypertrophy", "deadlift off-floor",
                    "deadlift lockout", "coordination/control"})
_PRESS = frozenset({"bench pec strength", "triceps strength"})
_GENERAL = frozenset({"general hypertrophy", "upper-back stability", "bench stability",
                      "low-fatigue technical support"})


def _values(value: Any) -> set[str]:
    if not value:
        return set()
    if isinstance(value, (list, tuple, set, frozenset)):
        return {str(item).strip().casefold() for item in value if str(item).strip()}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return set()
    return _values(parsed) if isinstance(parsed, list) else set()


def purpose_for(exercise: Exercise) -> str:
    """Return a purpose only when structured metadata supports one."""
    declared = _values(exercise.technical_purposes)
    explicit = sorted(declared & PURPOSES)
    if explicit:
        return explicit[0]
    if (exercise.category or "").casefold() == "grip":
        return "low-fatigue technical support"
    pattern = (exercise.movement_pattern or "").strip().casefold().replace("-", "_")
    return _PATTERN_PURPOSE.get(pattern, "")


@dataclass(frozen=True)
class WeeklyAccessoryCandidate:
    exercise: Exercise
    state_score: int = 0
    state_provenance: tuple[dict[str, Any], ...] = ()
    state_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccessoryHistory:
    """Observed response to one previously programmed accessory."""

    exercise_id: int
    successful: bool = True
    tolerated: bool = True
    progressing: bool = True
    stalled: bool = False
    pain: bool = False
    compensation: bool = False
    carryover: bool = True
    adherence: bool = True


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
    athlete_level: str = "intermediate"
    dots: float | None = None
    weak_point_priorities: frozenset[str] = frozenset()
    history: tuple[AccessoryHistory, ...] = ()
    skill_capacity: str = "competent"
    stability_requirement: str = "balanced"


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
    """Select a coherent week, then distribute it across its sessions."""

    # These are weekly movement envelopes, not fatigue-unit shopping budgets.
    # More training days create placement options; they do not create work.
    WEEKLY_MOVEMENT_TARGET = {"low": 3, "medium": 6, "high": 9}

    def prescriptions_for(self, row: Exercise, context: WeeklyAccessoryContext) -> tuple[WeekPrescription, ...]:
        return self._prescriptions(row, purpose_for(row) or "coach-directed", context)

    def pinned_prescriptions_for(self, row: Exercise, context: WeeklyAccessoryContext) -> tuple[WeekPrescription, ...]:
        generated = self.prescriptions_for(row, context)
        return tuple(WeekPrescription(
            item.week, row.default_sets if row.default_sets is not None else item.sets,
            row.default_reps or item.reps,
            float(row.default_rpe) if row.default_rpe is not None else item.rpe,
            row.default_rest_seconds if row.default_rest_seconds is not None else item.rest_seconds,
        ) for item in generated)

    def place_pins(self, exercises: Sequence[Exercise], context: WeeklyAccessoryContext,
                   *, explicit_day_indices: Sequence[int | None] | None = None) -> tuple[PlannedAccessory, ...]:
        self._validate(context)
        placements = tuple((None,) * len(exercises) if explicit_day_indices is None else explicit_day_indices)
        if len(placements) != len(exercises):
            raise ValueError("Each pin must have one explicit placement value.")
        loads = [0] * len(context.day_types)
        result = []
        for order, (row, fixed) in enumerate(zip(exercises, placements)):
            purpose = purpose_for(row) or "coach-directed"
            if fixed is not None and not 0 <= fixed < len(loads):
                raise ValueError("Coach-authored accessory day is outside the week.")
            day = fixed if fixed is not None else self._best_day(row, purpose, context, loads)
            warning = () if fixed is not None or self._day_allowed(row, purpose, context, day, loads) else (
                "Coach review: no clean session placement exists; the authoritative pin was preserved.",)
            result.append(PlannedAccessory(
                row, day, purpose, "Coach-pinned choice is authoritative.",
                self.pinned_prescriptions_for(row, context), warning,
            ))
            loads[day] += 1
        return tuple(result)

    def constraint_conflict(self, row: Exercise, constraints: frozenset[str]) -> bool:
        if constraints & _values(row.constraint_tags):
            return True
        active = {item.casefold().replace("-", "_") for item in constraints}
        pattern = (row.movement_pattern or "").casefold().replace("-", "_")
        tags = _values(row.compatibility_tags)
        cost = self._cost(row)
        if active & {"shoulder_loading", "elbow_loading", "shoulder", "elbow"}:
            if pattern in {"horizontal_press", "elbow_extension"} and not (
                tags & {"shoulder_compatible", "elbow_compatible"}
            ):
                return True
        if active & {"spinal_loading", "low_back_loading", "lower_back_loading", "low_back"}:
            if pattern in {
                "hinge", "hip_extension", "deadlift_off_floor",
                "deadlift_lockout", "squat",
            } and cost >= 3 and "low_back_compatible" not in tags:
                return True
        return False

    def plan(self, exercises: Iterable[Exercise | WeeklyAccessoryCandidate],
             context: WeeklyAccessoryContext) -> tuple[PlannedAccessory, ...]:
        self._validate(context)
        candidates = [item if isinstance(item, WeeklyAccessoryCandidate)
                      else WeeklyAccessoryCandidate(item) for item in exercises]
        history = {item.exercise_id: item for item in context.history}
        eligible = [item for item in candidates if self._eligible(item.exercise, context, history)]
        eligible.sort(key=lambda item: self._rank(item, context, history))

        taper = self._selection_taper(context)
        target = self.WEEKLY_MOVEMENT_TARGET.get(context.volume, 7)
        if context.dots is not None and context.dots >= 400:
            target = max(3, target - 2)
        if context.athlete_level.casefold() == "beginner":
            target = max(target, 5)
        if context.readiness_multiplier < .85:
            target = max(2, target - 2)
        if taper:
            target = max(1, (target + 1) // 2)

        chosen: list[WeeklyAccessoryCandidate] = []
        groups: set[str] = set()
        # Weak point priority is additive: reserve general development before
        # filling priority and remaining weekly slots.
        general = [item for item in eligible if purpose_for(item.exercise) in _GENERAL]
        priority = [item for item in eligible if self._priority_match(item.exercise, context)]
        for pool in (general[:2], priority, eligible):
            for item in pool:
                purpose = purpose_for(item.exercise)
                group = self._group(item.exercise, purpose)
                if item in chosen or group in groups or len(chosen) >= target:
                    continue
                chosen.append(item)
                groups.add(group)

        loads = [0] * len(context.day_types)
        placed: list[PlannedAccessory] = []
        demanding_days: set[int] = set()
        # Priority/high-skill work is placed and ordered first; dose/stability
        # manages its cost rather than burying it late.
        chosen.sort(key=lambda item: self._rank(item, context, history))
        for item in chosen:
            row = item.exercise
            purpose = purpose_for(row)
            day = self._best_day(row, purpose, context, loads)
            if self._demanding(row, purpose) and day in demanding_days:
                alternatives = [index for index in range(len(loads))
                                if index not in demanding_days and
                                self._day_allowed(row, purpose, context, index, loads)]
                day = min(alternatives, key=lambda index: (loads[index], index)) if alternatives else -1
            if day < 0:
                continue
            reason = self._reason(row, purpose, context, history.get(row.id))
            placed.append(PlannedAccessory(
                row, day, purpose, reason, self._prescriptions(row, purpose, context),
                state_score=item.state_score, state_provenance=item.state_provenance,
                state_reasons=item.state_reasons,
            ))
            loads[day] += 1
            if self._demanding(row, purpose):
                demanding_days.add(day)
        return tuple(sorted(placed, key=lambda item: (
            item.day_index, -int(self._priority_match(item.exercise, context)),
            -int(self._high_skill(item.exercise)), -item.state_score,
            -item.exercise.coach_priority, item.exercise.id,
        )))

    @staticmethod
    def _validate(context: WeeklyAccessoryContext) -> None:
        if not 1 <= len(context.day_types) <= 7:
            raise ValueError("Weekly accessory planning requires 1-7 training days.")

    def _eligible(self, row: Exercise, context: WeeklyAccessoryContext,
                  history: dict[int, AccessoryHistory]) -> bool:
        if not row.active or not row.accessory_suitable or not row.auto_select:
            return False
        if (row.category or "").casefold() in {"specialty", "strongman", "conditioning", "cardio"}:
            return False
        if ((row.category or "").casefold() == "grip" and
                context.competition_grip != "hook" and context.grip_work_priority == "none"):
            return False
        purpose = purpose_for(row)
        if not purpose:  # no semantic evidence means no automatic selection
            return False
        record = history.get(row.id)
        if record and (record.pain or not record.tolerated or record.compensation or not record.carryover or not record.adherence):
            return False
        if self.constraint_conflict(row, context.constraints):
            return False
        phases = _values(row.training_phases)
        if phases and not ({context.goal.casefold(), "all"} & phases):
            return False
        if context.available_equipment is not None:
            equipment = _values(row.equipment_options)
            if row.equipment:
                equipment.add(row.equipment.casefold())
            if equipment and not equipment & context.available_equipment:
                return False
        if self._selection_taper(context) and self._cost(row) >= 4:
            return False
        # Heavy split-squat semantics must be explicit; if present it is never
        # automatically forced into the already-dense SBD session.
        return True

    def _rank(self, candidate: WeeklyAccessoryCandidate, context: WeeklyAccessoryContext,
              history: dict[int, AccessoryHistory]) -> tuple[Any, ...]:
        row = candidate.exercise
        record = history.get(row.id)
        continuity = bool(record and record.successful and record.tolerated and
                          (record.progressing or not record.stalled))
        priority = self._priority_match(row, context)
        stable = self._stable(row)
        needs_stability = context.stability_requirement == "maximal_local_stimulus"
        skill_mismatch = context.skill_capacity.casefold() in {"beginner", "limited"} and self._high_skill(row)
        return (-int(continuity), -int(priority), -candidate.state_score,
                -int(needs_stability and stable), int(skill_mismatch),
                self._cost(row) if self._selection_taper(context) else 0,
                -row.coach_priority, self._cost(row), row.id)

    def _best_day(self, row: Exercise, purpose: str, context: WeeklyAccessoryContext,
                  loads: list[int]) -> int:
        choices = [i for i in range(len(loads)) if self._day_allowed(row, purpose, context, i, loads)]
        if not choices:
            return -1
        desired = "D" if (row.category or "").casefold() == "grip" else (
            "B" if purpose in _PRESS | {"bench stability", "upper-back stability", "general hypertrophy"} else (
            "S" if purpose in {"quad strength", "squat positional strength"} else "D" if purpose in _HINGE else "")
        )
        return min(choices, key=lambda i: (
            loads[i], -int(bool(desired and desired in context.day_types[i])),
            -int(context.day_types[i] == "B"), len(context.day_types[i]), i,
        ))

    def _day_allowed(self, row: Exercise, purpose: str, context: WeeklyAccessoryContext,
                     day: int, loads: list[int]) -> bool:
        if day < 0:
            return False
        day_type = context.day_types[day]
        cap = 2 if day_type == "SBD" else (4 if day_type == "B" else 3)
        if loads[day] >= cap:
            return False
        tags = _values(row.compatibility_tags) | _values(row.technical_purposes)
        heavy_split_squat = "heavy_split_squat" in tags or (
            (row.movement_pattern or "").casefold() == "split_squat" and self._cost(row) >= 4)
        if day_type == "SBD" and heavy_split_squat:
            return False
        return True

    @staticmethod
    def _group(row: Exercise, purpose: str) -> str:
        return (row.swap_group or row.variation_of or row.movement_pattern or f"purpose:{purpose}").casefold()

    @staticmethod
    def _cost(row: Exercise) -> int:
        return max(1, min(5, row.fatigue_rating or 3))

    @staticmethod
    def _demanding(row: Exercise, purpose: str) -> bool:
        return WeeklyAccessoryPlanner._cost(row) >= 4 or purpose in {
            "squat positional strength", "hip extension", "deadlift off-floor",
            "deadlift lockout", "bench pec strength",
        }

    @staticmethod
    def _stable(row: Exercise) -> bool:
        tags = _values(row.compatibility_tags) | _values(row.technical_purposes)
        return bool(tags & {"stable", "supported", "machine", "low_systemic_fatigue"})

    @staticmethod
    def _high_skill(row: Exercise) -> bool:
        tags = _values(row.compatibility_tags) | _values(row.technical_purposes)
        return bool(tags & {"high_skill", "coordination", "unstable"}) or purpose_for(row) == "coordination/control"

    @staticmethod
    def _priority_match(row: Exercise, context: WeeklyAccessoryContext) -> bool:
        if not context.weak_point_priorities:
            return False
        evidence = _values(row.technical_purposes) | _values(row.compatibility_tags) | {purpose_for(row)}
        return bool(context.weak_point_priorities & evidence)

    def _reason(self, row: Exercise, purpose: str, context: WeeklyAccessoryContext,
                history: AccessoryHistory | None) -> str:
        parts = [f"Weekly purpose: {purpose}."]
        if history and history.successful and history.tolerated:
            parts.append("Reused because prior response was successful and tolerated.")
        if self._priority_match(row, context):
            parts.append("Matches an explicit multi-signal weak-point priority.")
        if self._stable(row):
            parts.append("Stable setup supports local stimulus with controlled systemic cost.")
        return " ".join(parts)

    @staticmethod
    def _prescriptions(row: Exercise, purpose: str,
                       context: WeeklyAccessoryContext) -> tuple[WeekPrescription, ...]:
        compound = WeeklyAccessoryPlanner._cost(row) >= 4
        sets = row.default_sets if row.default_sets is not None else 2
        reps = row.default_reps or ("8-10" if compound else "10-15")
        rpe = float(row.default_rpe) if row.default_rpe is not None else (7.0 if compound else 8.0)
        rest = row.default_rest_seconds or (180 if compound else 90)
        result = []
        for week in range(1, context.week_count + 1):
            week_sets, week_rpe = sets, rpe
            days_to_meet = ((context.meet_date - date.today()).days - (week - 1) * 7
                            if context.meet_date else None)
            taper = ((days_to_meet is not None and days_to_meet <= 14) or
                     (context.goal == "peaking" and week >= max(1, context.week_count - 1)))
            if taper:
                week_sets = max(1, sets - (2 if compound else 1))
                week_rpe = min(7.0, rpe)
            if context.readiness_multiplier < .85:
                week_sets = max(1, week_sets - 1)
                week_rpe = max(5.0, week_rpe - .5)
            # No invented progression: absent observed response, all normal
            # weeks retain the same dose and rep range.
            result.append(WeekPrescription(week, week_sets, reps, week_rpe, rest))
        return tuple(result)

    @staticmethod
    def _selection_taper(context: WeeklyAccessoryContext) -> bool:
        if context.goal == "peaking":
            return True
        return bool(context.meet_date and
                    (context.meet_date - date.today()).days <= 7 * context.week_count)
