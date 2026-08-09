from decimal import Decimal

import pytest

from portal.services.meal_plans import (
    CoachOverride, DayMode, FoodSnapshot, MacroTotals, Meal, MealItem,
    MealPlanDay, MealPlanService, ReconciliationStatus, Substitution, reconcile,
)


def food(key, calories, protein, carbs, fat, fibre=0):
    return FoodSnapshot(key, key.title(), Decimal("100"), "g", MacroTotals(
        Decimal(str(calories)), Decimal(str(protein)), Decimal(str(carbs)),
        Decimal(str(fat)), Decimal(str(fibre)),
    ))


def item(key, source, amount="100"):
    return MealItem(key, source, Decimal(amount))


def test_portions_roll_up_in_declared_meal_order():
    oats = food("oats", 380, 13, 68, 7, 10)
    whey = food("whey", 400, 80, 8, 6)
    day = MealPlanDay("training", "Training", 1, DayMode.FIXED, (
        Meal("breakfast", "Breakfast", 1, (item("oats", oats, "50"), item("whey", whey, "25"))),
    ))

    assert day.planned_macros == MacroTotals(Decimal("290"), Decimal("26.5"), Decimal("36"), Decimal("5"), Decimal("5"))


def test_hybrid_day_reconciles_fixed_meals_plus_flexible_allowance():
    chicken = food("chicken", 200, 30, 0, 8)
    day = MealPlanDay("hybrid", "Hybrid", 1, DayMode.HYBRID,
        (Meal("lunch", "Lunch", 1, (item("chicken", chicken),)),),
        MacroTotals(1800, 120, 220, 52, 25))

    result = reconcile(day, MacroTotals(2000, 150, 220, 60, 25))

    assert result.status is ReconciliationStatus.MATCHED
    assert result.outside_fields == ()


def test_reconciliation_names_each_macro_outside_tolerance():
    day = MealPlanDay("flex", "Flexible", 1, DayMode.FLEXIBLE,
        flexible_target=MacroTotals(1800, 100, 200, 50, 20))

    result = reconcile(day, MacroTotals(2000, 150, 200, 60, 20))

    assert result.status is ReconciliationStatus.OUTSIDE_TOLERANCE
    assert result.outside_fields == ("calories", "protein_g", "fat_g")
    assert result.delta.protein_g == Decimal("-50")


def test_substitution_and_override_are_immutable_and_keep_slot_order():
    rice = food("rice", 130, 3, 28, 1)
    potato = food("potato", 90, 2, 20, 0)
    day = MealPlanDay("fixed", "Fixed", 1, DayMode.FIXED, (
        Meal("lunch", "Lunch", 1, (item("carb", rice), item("extra", rice))),
    ))
    service = MealPlanService()

    swapped = service.apply_substitution(day, Substitution("swap-1", "carb", item("potato-serving", potato), "Potato option"))
    overridden = service.apply_override(swapped, CoachOverride("override-1", "potato-serving", item("coach-carb", potato, "150"), "Higher training-day carbs", "coach-7"))

    assert [entry.item_id for entry in day.meals[0].items] == ["carb", "extra"]
    assert [entry.item_id for entry in overridden.meals[0].items] == ["coach-carb", "extra"]
    assert overridden.meals[0].macros.carbohydrate_g == Decimal("58")


def test_invalid_modes_duplicate_positions_and_unknown_targets_fail_loudly():
    with pytest.raises(ValueError, match="fixed days"):
        MealPlanDay("bad", "Bad", 1, DayMode.FIXED, flexible_target=MacroTotals(1))
    meal = Meal("one", "One", 1, ())
    with pytest.raises(ValueError, match="meal positions"):
        MealPlanDay("bad", "Bad", 1, DayMode.FIXED, (meal, Meal("two", "Two", 1, ())))
    with pytest.raises(ValueError, match="exactly once"):
        MealPlanService().apply_substitution(
            MealPlanDay("day", "Day", 1, DayMode.FIXED),
            Substitution("swap", "missing", item("new", food("x", 1, 1, 1, 1)), "Option"),
        )
