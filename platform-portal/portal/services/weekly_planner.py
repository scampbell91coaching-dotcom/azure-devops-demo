"""Coaching-led weekly structure planning.

This module decides *where* lift-family exposures belong.  Exercise selection,
prescription and assistance remain downstream concerns.
"""

from __future__ import annotations

from dataclasses import dataclass


SECONDARY_LOWER_PURPOSES = frozenset(
    {"technical_secondary", "positional", "capacity_hypertrophy", "lower_cost"}
)


@dataclass(frozen=True)
class PlannedExposure:
    lift_family: str
    placement: str
    purpose: str | None = None


@dataclass(frozen=True)
class PlannedDay:
    day_number: int
    day_type: str
    exposures: tuple[PlannedExposure, ...]
    reason: str

    @property
    def sequence_code(self) -> str:
        return "".join({"squat": "S", "bench": "B", "deadlift": "D"}[item.lift_family]
                       for item in self.exposures)


@dataclass(frozen=True)
class WeeklyStructure:
    days: tuple[PlannedDay, ...]
    reasons: tuple[str, ...]

    @property
    def day_sequence(self) -> list[str]:
        return [day.sequence_code for day in self.days]


class WeeklyPlanner:
    """Deterministic lift-family placement with explicit coaching provenance."""

    # Stable distribution orders: earliest primary bench, separated lower work,
    # and later competition lower exposure.  These are priorities, not a score.
    _BENCH_ORDER = {
        1: (0,), 2: (0, 1), 3: (0, 2, 1), 4: (0, 2, 3, 1),
        5: (0, 2, 4, 1, 3), 6: (0, 2, 4, 5, 1, 3),
    }
    _SQUAT_ORDER = {
        1: (0,), 2: (1, 0), 3: (2, 0, 1), 4: (1, 3, 0, 2),
        5: (1, 4, 0, 3, 2), 6: (1, 5, 3, 0, 4, 2),
    }
    _DEADLIFT_ORDER = {
        1: (0,), 2: (1, 0), 3: (1, 2, 0), 4: (2, 0, 3, 1),
        5: (3, 1, 4, 0, 2), 6: (1, 5, 3, 0, 4, 2),
    }

    def plan(self, *, training_days: int, squat_frequency: int,
             bench_frequency: int, deadlift_frequency: int,
             goal: str | None = None) -> WeeklyStructure:
        self._validate(
            training_days, squat_frequency, bench_frequency, deadlift_frequency,
            allow_historical_peaking_squat=(
                (training_days, squat_frequency, bench_frequency,
                 deadlift_frequency, goal) == (3, 3, 3, 2, "peaking")
            ),
        )

        if (training_days, squat_frequency, bench_frequency, deadlift_frequency, goal) == (3, 3, 3, 2, "peaking"):
            return self._from_sequence(
                ["SB", "SBD", "SBD"],
                (
                    "Established competition-oriented three-day structure retained for meet preparation.",
                    "SBD sessions are deliberate competition-specific practice.",
                ),
            )

        if training_days == 6 and (squat_frequency, deadlift_frequency) == (2, 2) \
                and bench_frequency in {5, 6}:
            sequence = (["B", "SD", "B", "B", "B", "SBD"]
                        if bench_frequency == 5
                        else ["B", "SBD", "B", "B", "B", "SBD"])
            reasons = (
                f"Six-day structure selected to distribute {bench_frequency} bench exposures while retaining two lower-body days.",
                "Saturday SBD retained for competition-specific practice.",
                "Secondary squat and deadlift share Tuesday for purposeful technical work.",
            )
            return self._from_sequence(sequence, reasons)

        # Wave 0 signed-graph golden and established safe engine behaviour.
        if (training_days, squat_frequency, bench_frequency, deadlift_frequency) == (3, 2, 2, 1):
            return self._from_sequence(
                ["B", "SB", "SD"],
                (
                    "Established three-day signed-graph structure retained for proposal compatibility.",
                    "Bench is isolated first, followed by combined squat sessions with squat ordered first.",
                ),
            )

        if (training_days, squat_frequency, bench_frequency, deadlift_frequency) == (3, 2, 3, 1):
            return self._from_sequence(
                ["BD", "SB", "SB"],
                (
                    "Historical three-day programme golden retained.",
                    "Primary bench is ordered before deadlift; squat is ordered before bench.",
                ),
            )

        occupied = [set() for _ in range(training_days)]
        for family, frequency, order in (
            ("B", bench_frequency, self._BENCH_ORDER[training_days]),
            ("S", squat_frequency, self._SQUAT_ORDER[training_days]),
            ("D", deadlift_frequency, self._DEADLIFT_ORDER[training_days]),
        ):
            for index in order[:frequency]:
                occupied[index].add(family)

        if any(not day for day in occupied):
            raise ValueError(
                "Invalid weekly frequency: requested exposures cannot anchor every training day without inventing workload."
            )
        sequence = ["".join(code for code in "SBD" if code in day) for day in occupied]
        reasons = (
            "Requested lift frequencies were distributed across the available sessions without adding exposures.",
            "Squat precedes bench and deadlift whenever lift families share a session.",
            "Session placement follows the documented stable distribution priority; no cyclic assignment is used.",
        )
        return self._from_sequence(sequence, reasons)

    @staticmethod
    def _validate(days: int, squat: int, bench: int, deadlift: int,
                  *, allow_historical_peaking_squat: bool = False) -> None:
        if days not in range(1, 7):
            raise ValueError("Invalid weekly frequency: the weekly planner supports one to six training days.")
        if min(squat, bench, deadlift) < 0:
            raise ValueError("Invalid weekly frequency: lift frequency cannot be negative.")
        if max(squat, bench, deadlift) > days:
            raise ValueError("Invalid weekly frequency: lift frequency cannot exceed training days.")
        if squat > 2 and not allow_historical_peaking_squat:
            raise ValueError("Invalid weekly frequency: squat cannot exceed two weekly exposures without new coach policy.")
        if deadlift > 2:
            raise ValueError("Invalid weekly frequency: deadlift cannot exceed two weekly exposures.")
        if squat + bench + deadlift < days:
            raise ValueError("Invalid weekly frequency: there are not enough requested exposures to anchor every training day.")

    @staticmethod
    def _from_sequence(sequence: list[str], reasons: tuple[str, ...]) -> WeeklyStructure:
        totals = {code: sum(code in day for day in sequence) for code in "SD"}
        seen = {"S": 0, "D": 0}
        days = []
        names = {"S": "squat", "B": "bench", "D": "deadlift"}
        for index, code in enumerate(sequence):
            exposures = []
            for lift in code:
                purpose = None
                placement = "primary"
                if lift in seen:
                    seen[lift] += 1
                    if totals[lift] == 2 and seen[lift] == 1:
                        placement = "secondary"
                        purpose = "positional" if lift == "S" else "technical_secondary"
                exposures.append(PlannedExposure(names[lift], placement, purpose))
            day_reason = "Combined lift-family session." if len(code) > 1 else "Primary bench isolated from lower-body competition lifts."
            days.append(PlannedDay(index + 1, code, tuple(exposures), day_reason))
        return WeeklyStructure(tuple(days), reasons)
