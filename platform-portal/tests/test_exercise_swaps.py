import json

from portal.models.exercise_library import Exercise
from portal.services.exercise_swaps import compatible_swaps


def exercise(name, *, specificity="close_variation", fatigue=4, equipment="barbell", constraints=()):
    return Exercise(
        name=name,
        movement="bench",
        category="variation",
        active=True,
        fatigue_rating=fatigue,
        lift_family="bench",
        movement_pattern="horizontal_press",
        specificity=specificity,
        swap_group="bench:horizontal_press",
        equipment_options=json.dumps([equipment]),
        constraint_tags=json.dumps(list(constraints)),
    )


def test_swap_candidates_preserve_group_and_explain_ordering():
    source = exercise("Paused Bench Press")
    source.id = 1
    close = exercise("Tempo Bench Press")
    close.id = 2
    different_fatigue = exercise("Dumbbell Bench Press", fatigue=2, equipment="dumbbells")
    different_fatigue.id = 3
    wrong_group = exercise("Cable Row")
    wrong_group.id = 4
    wrong_group.swap_group = "general:upper_pull"

    result = compatible_swaps(source, [different_fatigue, wrong_group, close])

    assert [item.exercise.name for item in result] == ["Tempo Bench Press", "Dumbbell Bench Press"]
    assert result[0].reasons == (
        "same swap group: bench:horizontal_press",
        "same specificity: close_variation",
        "same fatigue rating: 4/5",
        "equipment option available",
    )


def test_swap_candidates_honour_explicit_equipment_and_constraint_filters():
    source = exercise("Competition Bench Press", specificity="competition", equipment="barbell")
    source.id = 1
    supported = exercise("Machine Chest Press", equipment="machine", constraints=("externally_supported",))
    supported.id = 2
    barbell = exercise("Paused Bench Press", equipment="barbell")
    barbell.id = 3

    result = compatible_swaps(
        source,
        [supported, barbell],
        available_equipment={"machine"},
        excluded_constraint_tags={"externally_supported"},
    )

    assert result == []


def test_legacy_exercise_without_swap_group_has_no_automatic_candidates():
    source = Exercise(name="Coach exercise", movement="accessory", fatigue_rating=3)
    assert compatible_swaps(source, []) == []
