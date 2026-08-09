"""Schema-independent meal-plan domain and calculation services.

This module intentionally has no Flask, database, or food-provider dependency.
Macros are supplied by a coach-curated item snapshot and use ``Decimal`` so the
same rules can later sit behind HTML routes, JSON APIs, and persistence adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum
from typing import Iterable, Sequence


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

    def __post_init__(self) -> None:
        if not self.food_id.strip() or not self.name.strip() or not self.unit.strip():
            raise ValueError("food id, name, and unit are required")
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
