"""Schema-independent meal-plan domain and calculation services.

This module intentionally has no Flask, database, or food-provider dependency.
Macros are supplied by a coach-curated item snapshot and use ``Decimal`` so the
same rules can later sit behind HTML routes, JSON APIs, and persistence adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Callable, Iterable, Protocol, Sequence


ZERO = Decimal("0")


def _decimal(value: Decimal | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


class DayMode(str, Enum):
    FIXED = "fixed"
    FLEXIBLE = "flexible"
    HYBRID = "hybrid"


class ReconciliationStatus(str, Enum):
    MATCHED = "matched"
    OUTSIDE_TOLERANCE = "outside_tolerance"


@dataclass(frozen=True)
class MacroTotals:
    calories: Decimal = ZERO
    protein_g: Decimal = ZERO
    carbohydrate_g: Decimal = ZERO
    fat_g: Decimal = ZERO
    fibre_g: Decimal = ZERO

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, _decimal(getattr(self, name)))
        if any(value < 0 for value in self.values()):
            raise ValueError("macro values cannot be negative")

    def values(self) -> tuple[Decimal, ...]:
        return (self.calories, self.protein_g, self.carbohydrate_g, self.fat_g, self.fibre_g)

    def __add__(self, other: MacroTotals) -> MacroTotals:
        return MacroTotals(*(left + right for left, right in zip(self.values(), other.values())))

    def __sub__(self, other: MacroTotals) -> MacroDelta:
        return MacroDelta(*(left - right for left, right in zip(self.values(), other.values())))

    def scale(self, factor: Decimal | int | str) -> MacroTotals:
        factor = _decimal(factor)
        if factor < 0:
            raise ValueError("macro scale cannot be negative")
        return MacroTotals(*(value * factor for value in self.values()))


@dataclass(frozen=True)
class MacroDelta:
    """Signed difference between planned and target macro totals."""

    calories: Decimal = ZERO
    protein_g: Decimal = ZERO
    carbohydrate_g: Decimal = ZERO
    fat_g: Decimal = ZERO
    fibre_g: Decimal = ZERO

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, _decimal(getattr(self, name)))


@dataclass(frozen=True)
class FoodSnapshot:
    """Coach-curated nutrition facts for one declared reference portion."""

    food_id: str
    name: str
    reference_amount: Decimal
    unit: str
    macros: MacroTotals
    facts_revision: str = "1"

    def __post_init__(self) -> None:
        if not self.food_id.strip() or not self.name.strip() or not self.unit.strip():
            raise ValueError("food id, name, and unit are required")
        if not self.facts_revision.strip():
            raise ValueError("food facts revision is required")
        if self.reference_amount <= 0:
            raise ValueError("reference amount must be positive")


@dataclass(frozen=True)
class MealItem:
    item_id: str
    food: FoodSnapshot
    amount: Decimal
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.item_id.strip() or self.amount <= 0:
            raise ValueError("item id and a positive amount are required")

    @property
    def macros(self) -> MacroTotals:
        return self.food.macros.scale(self.amount / self.food.reference_amount)


@dataclass(frozen=True)
class Meal:
    meal_id: str
    name: str
    position: int
    items: tuple[MealItem, ...]
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.meal_id.strip() or not self.name.strip() or self.position < 1:
            raise ValueError("meal id, name, and positive position are required")
        ids = [item.item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("item ids must be unique within a meal")

    @property
    def macros(self) -> MacroTotals:
        return sum_macros(item.macros for item in self.items)


@dataclass(frozen=True)
class MealPlanDay:
    day_id: str
    name: str
    position: int
    mode: DayMode
    meals: tuple[Meal, ...] = ()
    flexible_target: MacroTotals = field(default_factory=MacroTotals)
    note: str | None = None

    def __post_init__(self) -> None:
        if not self.day_id.strip() or not self.name.strip() or self.position < 1:
            raise ValueError("day id, name, and positive position are required")
        positions = [meal.position for meal in self.meals]
        if len(positions) != len(set(positions)):
            raise ValueError("meal positions must be unique within a day")
        if self.mode is DayMode.FIXED and any(self.flexible_target.values()):
            raise ValueError("fixed days cannot have a flexible target")
        if self.mode is DayMode.FLEXIBLE and self.meals:
            raise ValueError("flexible days cannot contain fixed meals")
        if self.mode is DayMode.HYBRID and (not self.meals or not any(self.flexible_target.values())):
            raise ValueError("hybrid days require fixed meals and a flexible target")

    @property
    def fixed_macros(self) -> MacroTotals:
        return sum_macros(meal.macros for meal in self.meals)

    @property
    def planned_macros(self) -> MacroTotals:
        return self.fixed_macros + self.flexible_target


@dataclass(frozen=True)
class MacroTolerance:
    calories: Decimal = Decimal("50")
    protein_g: Decimal = Decimal("5")
    carbohydrate_g: Decimal = Decimal("10")
    fat_g: Decimal = Decimal("5")
    fibre_g: Decimal = Decimal("5")


@dataclass(frozen=True)
class Reconciliation:
    target: MacroTotals
    planned: MacroTotals
    delta: MacroDelta
    status: ReconciliationStatus
    outside_fields: tuple[str, ...]


@dataclass(frozen=True)
class Substitution:
    substitution_id: str
    target_item_id: str
    replacement: MealItem
    label: str

    def __post_init__(self) -> None:
        if not all((self.substitution_id.strip(), self.target_item_id.strip(), self.label.strip())):
            raise ValueError("substitution id, target, and label are required")


@dataclass(frozen=True)
class CoachOverride:
    override_id: str
    target_item_id: str
    replacement: MealItem
    reason: str
    actor_id: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.override_id, self.target_item_id, self.reason, self.actor_id)):
            raise ValueError("override id, target, reason, and actor are required")


def sum_macros(values: Iterable[MacroTotals]) -> MacroTotals:
    total = MacroTotals()
    for value in values:
        total = total + value
    return total


def reconcile(day: MealPlanDay, target: MacroTotals, tolerance: MacroTolerance = MacroTolerance()) -> Reconciliation:
    planned = day.planned_macros
    delta = planned - target
    fields = ("calories", "protein_g", "carbohydrate_g", "fat_g", "fibre_g")
    outside = tuple(name for name in fields if abs(getattr(delta, name)) > getattr(tolerance, name))
    return Reconciliation(target, planned, delta, ReconciliationStatus.OUTSIDE_TOLERANCE if outside else ReconciliationStatus.MATCHED, outside)


def replace_item(day: MealPlanDay, target_item_id: str, replacement: MealItem) -> MealPlanDay:
    """Return a new day, preserving meal order; fail on missing or ambiguous targets."""
    matches = sum(item.item_id == target_item_id for meal in day.meals for item in meal.items)
    if matches != 1:
        raise ValueError("target item must exist exactly once in the day")
    meals = tuple(
        replace(meal, items=tuple(replacement if item.item_id == target_item_id else item for item in meal.items))
        for meal in day.meals
    )
    return replace(day, meals=meals)


class MealPlanService:
    """Application-facing operations; repository and authorisation stay outside."""

    def apply_substitution(self, day: MealPlanDay, substitution: Substitution) -> MealPlanDay:
        if not substitution.substitution_id.strip() or not substitution.label.strip():
            raise ValueError("substitution id and label are required")
        return replace_item(day, substitution.target_item_id, substitution.replacement)

    def apply_override(self, day: MealPlanDay, override: CoachOverride) -> MealPlanDay:
        return replace_item(day, override.target_item_id, override.replacement)

    def validate_positions(self, days: Sequence[MealPlanDay]) -> None:
        positions = [day.position for day in days]
        if len(positions) != len(set(positions)):
            raise ValueError("day positions must be unique within a template")


class DraftStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


@dataclass(frozen=True)
class PrescriptionSnapshot:
    prescription_id: str
    revision: int
    targets: MacroTotals

    def __post_init__(self) -> None:
        if not self.prescription_id.strip() or self.revision < 1:
            raise ValueError("prescription identity and positive revision are required")


@dataclass(frozen=True)
class MealPlanDraft:
    template_id: str
    revision: int
    coach_id: str
    name: str
    days: tuple[MealPlanDay, ...] = ()
    substitutions: tuple[Substitution, ...] = ()
    notes: str | None = None
    status: DraftStatus = DraftStatus.DRAFT

    def __post_init__(self) -> None:
        if not all((self.template_id.strip(), self.coach_id.strip(), self.name.strip())):
            raise ValueError("template id, coach id, and name are required")
        if self.revision < 1:
            raise ValueError("revision must be positive")
        MealPlanService().validate_positions(self.days)
        ids = [day.day_id for day in self.days]
        if len(ids) != len(set(ids)):
            raise ValueError("day ids must be unique within a template")


@dataclass(frozen=True)
class DraftPreview:
    draft: MealPlanDraft
    prescription: PrescriptionSnapshot
    reconciliation: tuple[Reconciliation, ...]
    blocking_errors: tuple[str, ...]


@dataclass(frozen=True)
class PublishedAssignment:
    """Self-contained delivery record; never resolves live foods or prescriptions."""

    assignment_id: str
    athlete_id: int
    template_id: str
    template_revision: int
    days: tuple[MealPlanDay, ...]
    substitutions: tuple[Substitution, ...]
    prescription: PrescriptionSnapshot
    effective_from: date
    effective_until: date | None
    published_by: str
    published_at: datetime
    publication_note: str | None = None
    tolerance: MacroTolerance = field(default_factory=MacroTolerance)
    template_name: str | None = None

    def __post_init__(self) -> None:
        if not self.assignment_id.strip() or not self.published_by.strip():
            raise ValueError("assignment id and publisher are required")
        if self.athlete_id < 1 or self.template_revision < 1:
            raise ValueError("athlete and template revision must be positive")
        if self.effective_until is not None and self.effective_until < self.effective_from:
            raise ValueError("effective_until cannot precede effective_from")
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError("published_at must be timezone-aware")

    def is_effective_on(self, on_date: date) -> bool:
        return self.effective_from <= on_date and (self.effective_until is None or on_date <= self.effective_until)


class MealPlanRepository(Protocol):
    def get_draft(self, template_id: str) -> MealPlanDraft | None: ...
    def save_draft(self, draft: MealPlanDraft, expected_revision: int | None = None) -> None: ...
    def add_assignment(self, assignment: PublishedAssignment) -> None: ...
    def assignments_for(self, athlete_id: int) -> Sequence[PublishedAssignment]: ...


class WorkflowConflictError(ValueError):
    pass


class PublicationError(ValueError):
    pass


class InMemoryMealPlanRepository:
    def __init__(self) -> None:
        self._drafts: dict[str, MealPlanDraft] = {}
        self._assignments: list[PublishedAssignment] = []

    def get_draft(self, template_id: str) -> MealPlanDraft | None:
        return self._drafts.get(template_id)

    def save_draft(self, draft: MealPlanDraft, expected_revision: int | None = None) -> None:
        current = self._drafts.get(draft.template_id)
        if expected_revision is not None and (current is None or current.revision != expected_revision):
            raise WorkflowConflictError("draft revision is stale")
        self._drafts[draft.template_id] = draft

    def add_assignment(self, assignment: PublishedAssignment) -> None:
        if any(item.assignment_id == assignment.assignment_id for item in self._assignments):
            raise WorkflowConflictError("assignment id already exists")
        if any(_periods_overlap(item, assignment) for item in self._assignments if item.athlete_id == assignment.athlete_id):
            raise WorkflowConflictError("assignment effective period overlaps")
        self._assignments.append(assignment)

    def assignments_for(self, athlete_id: int) -> Sequence[PublishedAssignment]:
        return tuple(item for item in self._assignments if item.athlete_id == athlete_id)


class MealPlanWorkflow:
    def __init__(self, repository: MealPlanRepository, nutrition_enabled: Callable[[int], bool]) -> None:
        self.repository = repository
        self._nutrition_enabled = nutrition_enabled

    def save_draft(self, draft: MealPlanDraft, expected_revision: int | None = None) -> None:
        if draft.status is not DraftStatus.DRAFT:
            raise WorkflowConflictError("published revisions cannot be edited")
        self.repository.save_draft(draft, expected_revision)

    def preview(self, draft: MealPlanDraft, prescription: PrescriptionSnapshot, tolerance: MacroTolerance = MacroTolerance()) -> DraftPreview:
        errors: list[str] = []
        if not draft.days:
            errors.append("at least one day is required")
        results = tuple(reconcile(day, prescription.targets, tolerance) for day in draft.days)
        for day, result in zip(draft.days, results):
            if day.mode is not DayMode.FLEXIBLE and (not day.meals or any(not meal.items for meal in day.meals)):
                errors.append(f"{day.name}: every fixed meal requires an item")
            if result.status is ReconciliationStatus.OUTSIDE_TOLERANCE:
                errors.append(f"{day.name}: macros outside tolerance ({', '.join(result.outside_fields)})")
        return DraftPreview(draft, prescription, results, tuple(errors))

    def publish(self, *, assignment_id: str, athlete_id: int, draft: MealPlanDraft, prescription: PrescriptionSnapshot, effective_from: date, actor_id: str, effective_until: date | None = None, override_reason: str | None = None, tolerance: MacroTolerance = MacroTolerance(), now: datetime | None = None) -> PublishedAssignment:
        if not self._nutrition_enabled(athlete_id):
            raise PermissionError("nutrition coaching is not currently enabled")
        preview = self.preview(draft, prescription, tolerance)
        structural = tuple(error for error in preview.blocking_errors if "outside tolerance" not in error)
        mismatch = len(structural) != len(preview.blocking_errors)
        if structural:
            raise PublicationError("; ".join(structural))
        if mismatch and not (override_reason and override_reason.strip()):
            raise PublicationError("outside-tolerance publication requires an override reason")
        assignment = PublishedAssignment(assignment_id, athlete_id, draft.template_id, draft.revision, draft.days, draft.substitutions, prescription, effective_from, effective_until, actor_id, now or datetime.now(UTC), override_reason, tolerance, draft.name)
        self.repository.add_assignment(assignment)
        self.repository.save_draft(replace(draft, status=DraftStatus.PUBLISHED))
        return assignment

    def current_for_athlete(self, athlete_id: int, on_date: date) -> PublishedAssignment | None:
        # Current access/actions require entitlement. Historical reads do not.
        if not self._nutrition_enabled(athlete_id):
            return None
        matches = [item for item in self.repository.assignments_for(athlete_id) if item.is_effective_on(on_date)]
        if len(matches) > 1:
            raise WorkflowConflictError("multiple assignments are effective")
        return matches[0] if matches else None

    def historical_for_athlete(self, athlete_id: int) -> Sequence[PublishedAssignment]:
        return self.repository.assignments_for(athlete_id)

    def add_day(self, draft: MealPlanDraft, day: MealPlanDay) -> MealPlanDraft:
        return self._revise(draft, days=draft.days + (day,))

    def add_meal(self, draft: MealPlanDraft, day_id: str, meal: Meal) -> MealPlanDraft:
        days = tuple(replace(day, meals=day.meals + (meal,)) if day.day_id == day_id else day for day in draft.days)
        self._require_one(draft.days, lambda day: day.day_id == day_id, "day")
        return self._revise(draft, days=days)

    def add_item(self, draft: MealPlanDraft, meal_id: str, item: MealItem) -> MealPlanDraft:
        self._require_one((meal for day in draft.days for meal in day.meals), lambda meal: meal.meal_id == meal_id, "meal")
        days = tuple(replace(day, meals=tuple(replace(meal, items=meal.items + (item,)) if meal.meal_id == meal_id else meal for meal in day.meals)) for day in draft.days)
        return self._revise(draft, days=days)

    def set_portion(self, draft: MealPlanDraft, item_id: str, amount: Decimal | int | str) -> MealPlanDraft:
        self._require_one((item for day in draft.days for meal in day.meals for item in meal.items), lambda item: item.item_id == item_id, "item")
        days = tuple(replace(day, meals=tuple(replace(meal, items=tuple(replace(item, amount=_decimal(amount)) if item.item_id == item_id else item for item in meal.items)) for meal in day.meals)) for day in draft.days)
        return self._revise(draft, days=days)

    def add_substitution(self, draft: MealPlanDraft, substitution: Substitution) -> MealPlanDraft:
        self._require_one((item for day in draft.days for meal in day.meals for item in meal.items), lambda item: item.item_id == substitution.target_item_id, "item")
        if any(item.substitution_id == substitution.substitution_id for item in draft.substitutions):
            raise ValueError("substitution id must be unique")
        return self._revise(draft, substitutions=draft.substitutions + (substitution,))

    def set_notes(self, draft: MealPlanDraft, notes: str | None) -> MealPlanDraft:
        return self._revise(draft, notes=notes)

    def set_day_note(self, draft: MealPlanDraft, day_id: str, note: str | None) -> MealPlanDraft:
        self._require_one(draft.days, lambda day: day.day_id == day_id, "day")
        return self._revise(draft, days=tuple(replace(day, note=note) if day.day_id == day_id else day for day in draft.days))

    def set_meal_note(self, draft: MealPlanDraft, meal_id: str, note: str | None) -> MealPlanDraft:
        self._require_one((meal for day in draft.days for meal in day.meals), lambda meal: meal.meal_id == meal_id, "meal")
        days = tuple(replace(day, meals=tuple(replace(meal, note=note) if meal.meal_id == meal_id else meal for meal in day.meals)) for day in draft.days)
        return self._revise(draft, days=days)

    @staticmethod
    def _require_one(values: Iterable[object], predicate: Callable[[object], bool], label: str) -> None:
        if sum(1 for value in values if predicate(value)) != 1:
            raise ValueError(f"{label} must exist exactly once")

    @staticmethod
    def _revise(draft: MealPlanDraft, **changes: object) -> MealPlanDraft:
        if draft.status is not DraftStatus.DRAFT:
            raise WorkflowConflictError("published revisions cannot be edited")
        return replace(draft, revision=draft.revision + 1, **changes)


def _periods_overlap(left: PublishedAssignment, right: PublishedAssignment) -> bool:
    return (right.effective_until is None or left.effective_from <= right.effective_until) and (left.effective_until is None or right.effective_from <= left.effective_until)
