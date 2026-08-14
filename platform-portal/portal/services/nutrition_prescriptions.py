"""Schema-independent nutrition macro prescription domain.

This module models coach-authored targets only.  Actual intake, check-in answers,
and adherence belong to observation domains and must not be written here.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum
from typing import Protocol


class DayType(str, Enum):
    TRAINING = "training"
    REST = "rest"


MACRO_CALORIE_TOLERANCE = 50


@dataclass(frozen=True)
class MacroTargets:
    calories: int
    protein_g: int
    carbohydrate_g: int
    fat_g: int
    fibre_g: int | None = None

    @property
    def macro_calories(self) -> int:
        return (self.protein_g * 4) + (self.carbohydrate_g * 4) + (self.fat_g * 9)

    @property
    def calorie_delta(self) -> int:
        return self.macro_calories - self.calories

    def validate_calorie_alignment(
        self,
        tolerance: int = MACRO_CALORIE_TOLERANCE,
    ) -> None:
        delta = self.calorie_delta
        if abs(delta) <= tolerance:
            return

        direction = "above" if delta > 0 else "below"
        raise ValueError(
            f"Protein, carbohydrate and fat provide {self.macro_calories} kcal, "
            f"which is {abs(delta)} kcal {direction} the {self.calories} kcal target. "
            f"Keep macro-derived calories within ±{tolerance} kcal of the calorie target."
        )

    def __post_init__(self) -> None:
        limits = {
            "calories": (self.calories, 500, 10_000),
            "protein_g": (self.protein_g, 0, 500),
            "carbohydrate_g": (self.carbohydrate_g, 0, 1_000),
            "fat_g": (self.fat_g, 0, 400),
        }
        if self.fibre_g is not None:
            limits["fibre_g"] = (self.fibre_g, 0, 150)
        for name, (value, minimum, maximum) in limits.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")


@dataclass(frozen=True)
class PrescriptionProvenance:
    actor_id: str
    actor_role: str
    source: str = "coach_authored"
    source_reference: str | None = None
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        for name in ("actor_id", "actor_role", "source"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must be timezone-aware")


@dataclass(frozen=True)
class MacroPrescription:
    prescription_id: str
    athlete_id: int
    daily_targets: MacroTargets
    effective_from: date
    provenance: PrescriptionProvenance
    effective_until: date | None = None
    training_day_targets: MacroTargets | None = None
    rest_day_targets: MacroTargets | None = None
    meal_count: int | None = None
    notes: str | None = None
    revision: int = 1

    def __post_init__(self) -> None:
        if not self.prescription_id.strip():
            raise ValueError("prescription_id is required")
        if isinstance(self.revision, bool) or self.revision < 1:
            raise ValueError("revision must be positive")
        if isinstance(self.athlete_id, bool) or self.athlete_id < 1:
            raise ValueError("athlete_id must be positive")
        if self.effective_until is not None and self.effective_until < self.effective_from:
            raise ValueError("effective_until cannot precede effective_from")
        if self.meal_count is not None:
            if isinstance(self.meal_count, bool) or not 1 <= self.meal_count <= 12:
                raise ValueError("meal_count must be between 1 and 12")
        if self.notes is not None and len(self.notes) > 2_000:
            raise ValueError("notes cannot exceed 2000 characters")

    def is_effective_on(self, on_date: date) -> bool:
        return self.effective_from <= on_date and (
            self.effective_until is None or on_date <= self.effective_until
        )

    def targets_for(self, day_type: DayType | None = None) -> MacroTargets:
        if day_type is DayType.TRAINING and self.training_day_targets is not None:
            return self.training_day_targets
        if day_type is DayType.REST and self.rest_day_targets is not None:
            return self.rest_day_targets
        return self.daily_targets


class MacroPrescriptionRepository(Protocol):
    """Persistence seam: adapters exchange domain objects, never ORM rows."""

    def list_for_athlete(self, athlete_id: int) -> Sequence[MacroPrescription]: ...

    def add(self, prescription: MacroPrescription) -> None: ...


class PrescriptionConflictError(ValueError):
    pass


class InMemoryMacroPrescriptionRepository:
    """Configuration/test adapter; replaceable by a future database adapter."""

    def __init__(self, prescriptions: Iterable[MacroPrescription] = ()) -> None:
        self._prescriptions = list(prescriptions)

    def list_for_athlete(self, athlete_id: int) -> Sequence[MacroPrescription]:
        return tuple(
            item for item in self._prescriptions if item.athlete_id == athlete_id
        )

    def add(self, prescription: MacroPrescription) -> None:
        self._prescriptions.append(prescription)


@dataclass(frozen=True)
class ResolvedMacroTargets:
    prescription_id: str
    athlete_id: int
    effective_on: date
    day_type: DayType | None
    targets: MacroTargets
    meal_count: int | None
    notes: str | None
    provenance: PrescriptionProvenance
    revision: int


class MacroPrescriptionService:
    def __init__(self, repository: MacroPrescriptionRepository) -> None:
        self._repository = repository

    def assign(self, prescription: MacroPrescription) -> None:
        existing = self._repository.list_for_athlete(prescription.athlete_id)
        duplicate = next(
            (
                item
                for item in existing
                if item.prescription_id == prescription.prescription_id
            ),
            None,
        )
        if duplicate is not None:
            raise PrescriptionConflictError("prescription_id already exists")
        overlap = next(
            (item for item in existing if _periods_overlap(item, prescription)), None
        )
        if overlap is not None:
            raise PrescriptionConflictError(
                f"effective period overlaps prescription {overlap.prescription_id}"
            )
        self._repository.add(prescription)

    def history(self, athlete_id: int) -> Sequence[MacroPrescription]:
        """Return every immutable version in repository-defined display order."""
        return self._repository.list_for_athlete(athlete_id)

    def prescription_on(
        self, athlete_id: int, on_date: date
    ) -> MacroPrescription | None:
        matches = [
            item
            for item in self._repository.list_for_athlete(athlete_id)
            if item.is_effective_on(on_date)
        ]
        if len(matches) > 1:
            raise PrescriptionConflictError(
                "multiple prescriptions are effective; persistence data is ambiguous"
            )
        return matches[0] if matches else None

    def resolve(
        self, athlete_id: int, on_date: date, day_type: DayType | None = None
    ) -> ResolvedMacroTargets | None:
        prescription = self.prescription_on(athlete_id, on_date)
        if prescription is None:
            return None
        return ResolvedMacroTargets(
            prescription_id=prescription.prescription_id,
            athlete_id=athlete_id,
            effective_on=on_date,
            day_type=day_type,
            targets=prescription.targets_for(day_type),
            meal_count=prescription.meal_count,
            notes=prescription.notes,
            provenance=prescription.provenance,
            revision=prescription.revision,
        )


def _periods_overlap(
    left: MacroPrescription, right: MacroPrescription
) -> bool:
    return (
        right.effective_until is None
        or left.effective_from <= right.effective_until
    ) and (
        left.effective_until is None
        or right.effective_from <= left.effective_until
    )
