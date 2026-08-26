"""Purpose, stress and phase-led main-lift prescription planning."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrescriptionContext:
    purpose: str
    stress_role: str
    phase: str
    week: int
    week_count: int
    target_rpe: float
    allocated_sets: int
    athlete_level: str | None = None
    meet_proximity_days: int | None = None
    structure_preference: str | None = None


@dataclass(frozen=True)
class PrescriptionComponent:
    role: str
    sets: int
    reps: str
    rpe: float


@dataclass(frozen=True)
class PlannedPrescription:
    structure: str
    components: tuple[PrescriptionComponent, ...]
    reason: str

    @property
    def sets(self) -> int:
        return sum(item.sets for item in self.components)


class PrescriptionPlanner:
    """Plan dose without deriving semantics from the exercise name."""

    def plan(self, context: PrescriptionContext) -> PlannedPrescription:
        purpose, role = context.purpose, context.stress_role
        near_meet = context.phase == "peaking" or (
            context.meet_proximity_days is not None and context.meet_proximity_days <= 28
        )
        sets = max(1, context.allocated_sets)

        if purpose == "competition_intensity" and role == "hard":
            reps = "1" if near_meet else "2-3"
            rpe = self._rpe(context.target_rpe + 0.5)
            if context.structure_preference == "top_set_backoffs" and sets >= 2:
                components = (
                    PrescriptionComponent("top_set", 1, reps, rpe),
                    PrescriptionComponent("backoff", sets - 1, "3" if near_meet else "4", self._rpe(rpe - 1.0)),
                )
                return PlannedPrescription("top_set_backoffs", components,
                    "Top set plus backoffs selected for intensity-led competition exposure.")
            return PlannedPrescription("straight_sets", (
                PrescriptionComponent("work", sets, reps, rpe),),
                "Straight sets selected for intensity-led competition exposure.")

        if purpose == "competition_volume" and role == "hard":
            reps = "3-4" if near_meet else "5-6"
            return PlannedPrescription("straight_sets", (
                PrescriptionComponent("work", sets, reps, self._rpe(context.target_rpe - 0.5)),),
                "Volume-led competition work uses more repetitions at controlled effort.")

        if role == "lower_stress":
            sets = min(3, max(2, sets))
            reps = "5" if near_meet else "6"
            return PlannedPrescription("straight_sets", (
                PrescriptionComponent("work", sets, reps, min(7.0, self._rpe(context.target_rpe - 1.0))),),
                f"{sets}x{reps} selected as lower-stress {purpose.replace('_', ' ')} volume.")

        settings = {
            "technical_secondary": ("4", -1.0, "Technical dose prioritises quality without unnecessary fatigue."),
            "positional": ("5", -0.5, "Moderate positional dose emphasises execution and control."),
            "capacity_hypertrophy": ("6-8", -0.5, "Additional controlled volume serves capacity and hypertrophy."),
            "lower_cost": ("5-6", -1.0, "Dose is reduced to limit systemic cost."),
        }
        reps, offset, reason = settings.get(purpose, ("3", 0.0, "Competition-specific dose follows phase and target effort."))
        if near_meet and purpose == "competition":
            # The upstream weekly volume envelope already owns set-count
            # reductions; this boundary increases specificity without applying
            # a second, hidden taper.
            reps = "1-2"
        return PlannedPrescription("straight_sets", (
            PrescriptionComponent("work", sets, reps, self._rpe(context.target_rpe + offset)),), reason)

    @staticmethod
    def _rpe(value: float) -> float:
        return max(1.0, min(10.0, round(value * 2) / 2))
