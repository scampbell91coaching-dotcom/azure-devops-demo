"""Deterministic coaching intent for generated powerlifting exposures."""

from __future__ import annotations

from dataclasses import dataclass


EXPOSURE_ROLES = frozenset({
    "competition",
    "primary_volume",
    "secondary_strength",
    "technique",
    "low_fatigue",
    "overload",
})


@dataclass(frozen=True)
class ExposureIntent:
    lift_family: str
    role: str
    exercise_name: str
    sets: int
    reps: str
    rpe_offset: float
    purpose: str


_ROLE_ORDER = (
    "primary_volume", "secondary_strength", "technique", "low_fatigue",
)

_VARIATIONS = {
    "squat": {
        "competition": "Competition Squat",
        "primary_volume": "High-Bar Back Squat",
        "secondary_strength": "Pause Squat",
        "technique": "Tempo Squat",
        "low_fatigue": "Belt Squat",
        "overload": "Pin Squat",
    },
    "bench": {
        "competition": "Competition Bench Press",
        "primary_volume": "Close-Grip Bench Press",
        "secondary_strength": "Paused Bench Press",
        "technique": "Tempo Bench Press",
        "low_fatigue": "Feet-Up Bench Press",
        "overload": "Slingshot Bench Press",
    },
    "deadlift": {
        "competition": "Competition Deadlift",
        "primary_volume": "Romanian Deadlift",
        "secondary_strength": "Paused Deadlift",
        "technique": "Tempo Deadlift",
        "low_fatigue": "Romanian Deadlift",
        "overload": "Block Pull",
    },
}

_PRESCRIPTIONS = {
    "competition": (3, "3", 0.5, "competition practice"),
    "primary_volume": (4, "6", -0.5, "primary volume"),
    "secondary_strength": (3, "4", 0.0, "secondary strength"),
    "technique": (3, "5", -1.0, "technical practice"),
    "low_fatigue": (2, "6", -1.5, "low-fatigue practice"),
    "overload": (2, "2", 1.0, "overload strength"),
}


def weekly_exposure_intents(
    day_sequence: list[str], *, goal: str, deadlift_style: str
) -> list[list[ExposureIntent]]:
    """Assign explicit intent while keeping the supplied schedule authoritative."""
    positions = {
        code: [
            (day_index, code_index)
            for day_index, day in enumerate(day_sequence)
            for code_index, value in enumerate(day)
            if value == code
        ]
        for code in "SBD"
    }
    roles: dict[tuple[int, int], str] = {}
    for code, occurrences in positions.items():
        if not occurrences:
            continue
        # The final SBD day is the preferred competition-specific exposure.
        competition = next(
            (item for item in reversed(occurrences) if day_sequence[item[0]] == "SBD"),
            occurrences[-1],
        )
        roles[competition] = "competition"
        available = list(_ROLE_ORDER)
        if goal == "peaking":
            available[1] = "overload"
        for index, item in enumerate(
            item for item in occurrences if item != competition
        ):
            roles[item] = available[index % len(available)]

    family_by_code = {"S": "squat", "B": "bench", "D": "deadlift"}
    result: list[list[ExposureIntent]] = []
    for day_index, day in enumerate(day_sequence):
        day_intents = []
        for code_index, code in enumerate(day):
            family = family_by_code[code]
            role = roles[(day_index, code_index)]
            exercise_name = _VARIATIONS[family][role]
            if family == "deadlift" and role == "competition":
                exercise_name = (
                    "Sumo Deadlift" if deadlift_style == "sumo"
                    else "Conventional Deadlift"
                )
            sets, reps, rpe_offset, purpose = _PRESCRIPTIONS[role]
            day_intents.append(ExposureIntent(
                family, role, exercise_name, sets, reps, rpe_offset, purpose
            ))
        result.append(day_intents)
    return result
