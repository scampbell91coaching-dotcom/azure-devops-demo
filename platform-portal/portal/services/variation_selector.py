"""Conservative, purpose-led powerlifting variation selection.

Catalogue taxonomy is not yet decision-grade, so automatic selection is limited
to the coach-confirmed mappings below.  Ordering is policy, never randomness or
a catalogue score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class CoachSelectionRequired(ValueError):
    """Raised when no safe automatic selection can serve the requested purpose."""


@dataclass(frozen=True)
class VariationContext:
    lift_family: str
    purpose: str
    stress_role: str
    available_exercises: tuple[str, ...] = ()
    coach_pinned_exercise: str | None = None
    athlete_level: str | None = None
    technical_issue: str | None = None
    sticking_pattern: str | None = None
    pain_or_tolerance: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    explicit_coach_flag: str | None = None


@dataclass(frozen=True)
class VariationSelection:
    exercise_name: str
    reason: str
    provenance: str


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


# Aliases are intentionally explicit: incomplete catalogue fields are not used
# to manufacture powerlifting semantics.
_ALIASES = {
    "competition bench": "Competition Bench Press",
    "competition bench press": "Competition Bench Press",
    "bench press": "Competition Bench Press",
    "pause bench": "Paused Bench Press",
    "paused bench": "Paused Bench Press",
    "paused bench press": "Paused Bench Press",
    "2 count pause bench": "2-Count Pause Bench Press",
    "3 count pause bench": "3-Count Pause Bench Press",
    "spoto": "Spoto Press", "spoto press": "Spoto Press",
    "incline": "Incline Bench Press", "incline bench": "Incline Bench Press",
    "incline bench press": "Incline Bench Press",
    "larsen": "Larsen Press", "larsen press": "Larsen Press",
    "close grip bench": "Close-Grip Bench Press",
    "close grip bench press": "Close-Grip Bench Press",
    "competition squat": "Competition Squat", "squat": "Competition Squat",
    "pause squat": "Pause Squat", "paused squat": "Pause Squat",
    "tempo squat": "Tempo Squat", "tempo pause squat": "Tempo-Pause Squat",
    "competition deadlift": "Competition Deadlift", "deadlift": "Competition Deadlift",
    "conventional deadlift": "Conventional Deadlift", "sumo deadlift": "Sumo Deadlift",
    "pause deadlift": "Paused Deadlift", "paused deadlift": "Paused Deadlift",
    "tempo deadlift": "Tempo Deadlift", "rdl": "Romanian Deadlift",
    "romanian deadlift": "Romanian Deadlift", "trap bar deadlift": "Trap Bar Deadlift",
}

_PURPOSE_ORDER = {
    ("bench", "competition_intensity"): ("competition bench press",),
    ("bench", "competition_volume"): ("competition bench press",),
    ("bench", "competition"): ("competition bench press",),
    ("bench", "technical"): ("pause bench", "2 count pause bench", "3 count pause bench"),
    ("bench", "pause_control"): ("2 count pause bench", "3 count pause bench", "pause bench"),
    ("bench", "positional"): ("spoto press", "pause bench"),
    ("bench", "hypertrophy"): ("incline bench", "larsen press"),
    ("bench", "development"): ("larsen press", "incline bench", "close grip bench"),
    ("bench", "low_cost"): ("larsen press", "incline bench"),
    ("squat", "competition"): ("competition squat",),
    ("squat", "technical_secondary"): ("pause squat", "tempo squat"),
    ("squat", "positional"): ("pause squat", "tempo pause squat", "tempo squat"),
    ("deadlift", "competition"): ("competition deadlift",),
    ("deadlift", "technical_secondary"): ("pause deadlift", "tempo deadlift"),
    ("deadlift", "positional"): ("pause deadlift", "tempo deadlift"),
    ("deadlift", "capacity_hypertrophy"): ("rdl", "trap bar deadlift"),
    ("deadlift", "lower_cost"): ("rdl", "trap bar deadlift"),
}


class VariationSelector:
    """Select the first safe, available movement for an explicit purpose."""

    def select(self, context: VariationContext) -> VariationSelection:
        if context.coach_pinned_exercise and context.coach_pinned_exercise.strip():
            return VariationSelection(
                context.coach_pinned_exercise.strip(),
                "Coach-pinned exercise preserved as authoritative.", "coach_selected",
            )

        family, purpose = context.lift_family.casefold(), context.purpose.casefold()
        if context.stress_role == "hard" and family == "bench":
            purpose = "competition_intensity" if purpose == "competition_intensity" else "competition_volume"

        order = _PURPOSE_ORDER.get((family, purpose))
        # Beginners receive broad competition practice unless a simple technical
        # variant is explicitly warranted; no sticking-point diagnosis is made.
        if context.athlete_level == "beginner" and purpose not in {
            "technical", "technical_secondary", "pause_control", "positional",
        }:
            order = _PURPOSE_ORDER.get((family, "competition"), order)
        if not order:
            return self._competition_fallback(context)

        available = {_key(name): name for name in context.available_exercises if name.strip()}
        for alias in order:
            canonical = _ALIASES[_key(alias)]
            if not available:
                return self._selected(context, canonical)
            for key, actual in available.items():
                if _ALIASES.get(key, actual) == canonical:
                    return self._selected(context, actual)
        return self._competition_fallback(context)

    @staticmethod
    def _selected(context: VariationContext, name: str) -> VariationSelection:
        labels = {
            ("deadlift", "technical_secondary"): "technical secondary work targeting start-position control",
            ("deadlift", "capacity_hypertrophy"): "capacity/hypertrophy without adding another competition pull",
            ("squat", "positional"): "positional reinforcement",
            ("bench", "positional"): "lower-stress positional bench work",
            ("bench", "technical"): "lower-stress pause/control practice",
        }
        detail = labels.get((context.lift_family, context.purpose), context.purpose.replace("_", " "))
        return VariationSelection(name, f"{name} selected for {detail}.", "known_safe_mapping")

    def _competition_fallback(self, context: VariationContext) -> VariationSelection:
        competition = {
            "bench": "Competition Bench Press", "squat": "Competition Squat",
            "deadlift": "Competition Deadlift",
        }.get(context.lift_family)
        compatible = not context.pain_or_tolerance
        available = tuple(context.available_exercises)
        deadlift_competition = context.lift_family == "deadlift" and next((
            item for item in available if _key(item) in {
                "competition deadlift", "conventional deadlift", "sumo deadlift", "deadlift"
            }
        ), None)
        if competition and compatible and (not available or deadlift_competition or any(
            _ALIASES.get(_key(item), item) == competition for item in available
        )):
            actual = deadlift_competition or next((item for item in available if _ALIASES.get(_key(item), item) == competition), competition)
            return VariationSelection(
                actual,
                f"No safe {context.purpose.replace('_', ' ')} variation was available; compatible competition lift retained.",
                "competition_fallback",
            )
        raise CoachSelectionRequired(
            f"Coach selection required: no safe {context.lift_family} variation matches purpose '{context.purpose}'."
        )
