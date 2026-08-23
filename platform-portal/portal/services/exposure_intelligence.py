"""Purpose-led coaching intent for generated powerlifting exposures.

The signed proposal stores the complete intent.  ``legacy_role`` is only the
projection required by the existing ``ProgrammingLiftSlot.exposure_role``
column; it is not used to make coaching decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class WeeklySkeleton(Protocol):
    @property
    def day_sequence(self) -> list[str]: ...


@dataclass(frozen=True)
class ExposureIntent:
    lift_family: str
    purpose: str
    stress_role: str
    legacy_role: str
    # Read-only compatibility spelling for preview consumers from Waves 0/1.
    role: str
    exercise_name: str
    sets: int
    reps: str
    rpe_offset: float
    rpe_cap: float | None
    reason: str


_BENCH_LOWER_STRESS = (
    ("technical", "Tempo Bench Press", "technique",
     "Lower-stress bench: technical practice."),
    ("positional", "Paused Bench Press", "secondary_strength",
     "Lower-stress bench: positional practice."),
    ("hypertrophy", "Close-Grip Bench Press", "primary_volume",
     "Lower-stress bench: hypertrophy development."),
    ("low_cost", "Feet-Up Bench Press", "low_fatigue",
     "Lower-stress bench: low-cost development."),
)


def _bench_intents(
    day_sequence: list[str], occurrences: list[tuple[int, int]]
) -> dict[tuple[int, int], ExposureIntent]:
    if not occurrences:
        return {}

    sbd = next(
        (item for item in reversed(occurrences)
         if len(day_sequence[item[0]]) == 3
         and set(day_sequence[item[0]]) == {"S", "B", "D"}),
        None,
    )

    def primary_suitable(item: tuple[int, int]) -> bool:
        # Primary bench may be first or immediately after squat, never after D.
        before = day_sequence[item[0]][:item[1]]
        return before in {"", "S"}

    suitable = [item for item in occurrences if primary_suitable(item)]
    if not suitable:
        raise ValueError("No bench exposure has a valid primary placement.")

    if sbd is not None and primary_suitable(sbd):
        intensity = sbd
        second = next((item for item in suitable if item != sbd), None)
        second_reason = "Second hard competition bench: volume-led exposure."
    else:
        intensity = suitable[0]
        before_sbd = [item for item in suitable if sbd is not None and item[0] < sbd[0]]
        second = next((item for item in reversed(before_sbd) if item != intensity), None)
        if second is None:
            second = next((item for item in reversed(suitable) if item != intensity), None)
        second_reason = "Second hard competition bench: volume-led exposure before SBD."

    result = {
        intensity: ExposureIntent(
            "bench", "competition_intensity", "hard", "competition", "competition",
            "Competition Bench Press", 3, "3", 0.5, None,
            "Primary competition bench: intensity-led exposure.",
        )
    }
    if second is not None:
        result[second] = ExposureIntent(
            "bench", "competition_volume", "hard", "primary_volume", "primary_volume",
            "Competition Bench Press", 4, "6", -0.5, None, second_reason,
        )
    for index, item in enumerate(item for item in occurrences if item not in result):
        purpose, exercise, legacy, reason = _BENCH_LOWER_STRESS[index % len(_BENCH_LOWER_STRESS)]
        result[item] = ExposureIntent(
            "bench", purpose, "lower_stress", legacy, legacy, exercise,
            2 + (index % 2), str(5 + (index % 4)), -1.0, 7.0, reason,
        )
    return result


def _lower_lift_intents(
    family: str,
    occurrences: list[tuple[int, int]],
    day_sequence: list[str],
    deadlift_style: str,
) -> dict[tuple[int, int], ExposureIntent]:
    if family == "deadlift" and len(occurrences) > 2:
        raise ValueError("Deadlift cannot exceed two weekly exposures.")
    if not occurrences:
        return {}
    competition = next(
        (item for item in reversed(occurrences) if day_sequence[item[0]] == "SBD"),
        occurrences[-1],
    )
    competition_exercise = "Competition Squat"
    if family == "deadlift":
        competition_exercise = "Sumo Deadlift" if deadlift_style == "sumo" else "Conventional Deadlift"
    result = {competition: ExposureIntent(
        family, "competition", "primary", "competition", "competition", competition_exercise,
        3, "3", 0.5, None,
        f"Primary competition {family}: competition-specific exposure.",
    )}
    for item in (value for value in occurrences if value != competition):
        if family == "deadlift":
            result[item] = ExposureIntent(
                family, "technical_secondary", "secondary", "secondary_strength", "secondary_strength",
                "Paused Deadlift", 3, "4", -0.5, 8.0,
                "Paused deadlift: technical secondary exposure for start-position practice.",
            )
        else:
            result[item] = ExposureIntent(
                family, "positional", "secondary", "secondary_strength", "secondary_strength",
                "Pause Squat", 3, "5", -0.5, 8.0,
                "Paused squat: positional secondary exposure.",
            )
    return result


def weekly_exposure_intents(
    day_sequence: list[str] | WeeklySkeleton, *, goal: str, deadlift_style: str
) -> list[list[ExposureIntent]]:
    """Plan lift placement and explicit purpose without using legacy role rotation."""
    if not isinstance(day_sequence, list):
        day_sequence = day_sequence.day_sequence
    del goal  # Reserved for later purpose-aware variation/prescription planners.
    positions = {
        code: [(day_index, code_index)
               for day_index, day in enumerate(day_sequence)
               for code_index, value in enumerate(day) if value == code]
        for code in "SBD"
    }
    planned: dict[tuple[int, int], ExposureIntent] = {}
    planned.update(_bench_intents(day_sequence, positions["B"]))
    planned.update(_lower_lift_intents(
        "squat", positions["S"], day_sequence, deadlift_style
    ))
    planned.update(_lower_lift_intents(
        "deadlift", positions["D"], day_sequence, deadlift_style
    ))
    return [[planned[(day_index, code_index)] for code_index, _ in enumerate(day)]
            for day_index, day in enumerate(day_sequence)]
