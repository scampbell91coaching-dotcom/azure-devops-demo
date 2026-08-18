"""Realistic golden programmes for Traditional Strength Accessory Intelligence V2."""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from portal.models.exercise_library import Exercise
from portal.services.weekly_accessory_planner import (
    PURPOSES, WeeklyAccessoryCandidate, WeeklyAccessoryContext,
    WeeklyAccessoryPlanner,
)


def exercise(name, *, priority, fatigue, relevance="all", pattern=None,
             equipment=None, constraints=(), auto=True, category="assistance",
             sets=None, reps=None, rpe=None, rest=None, purposes=(), compatible=()):
    return Exercise(
        id=priority, name=name, movement="accessory", category=category,
        active=True, accessory_suitable=True, auto_select=auto,
        coach_priority=priority, fatigue_rating=fatigue,
        lift_relevance=f'["{relevance}"]', movement_pattern=pattern,
        swap_group=f"golden:{pattern}" if pattern else None,
        equipment=equipment,
        equipment_options=f'["{equipment}"]' if equipment else None,
        constraint_tags=str(list(constraints)).replace("'", '"'),
        technical_purposes=str(list(purposes)).replace("'", '"'),
        compatibility_tags=str(list(compatible)).replace("'", '"'),
        default_sets=sets, default_reps=reps, default_rpe=rpe,
        default_rest_seconds=rest,
    )


GOLDEN_LIBRARY = (
    exercise("Leg Extension", priority=90, fatigue=1, relevance="squat", pattern="knee_extension", equipment="machine", reps="10-15", rest=75),
    exercise("Paused High-Bar Squat", priority=85, fatigue=4, relevance="squat", pattern="squat", equipment="barbell"),
    exercise("Barbell Hip Thrust", priority=80, fatigue=3, relevance="deadlift", pattern="hip_extension", equipment="barbell"),
    exercise("Seated Leg Curl", priority=75, fatigue=2, relevance="deadlift", pattern="knee_flexion", equipment="machine"),
    exercise("Chest-Supported Row", priority=70, fatigue=2, relevance="bench", pattern="horizontal_pull", equipment="dumbbell"),
    exercise("Dumbbell Bench Press", priority=65, fatigue=3, relevance="bench", pattern="horizontal_press", equipment="dumbbell"),
    exercise("Cable Triceps Extension", priority=60, fatigue=1, relevance="bench", pattern="elbow_extension", equipment="cable"),
    exercise("Cable Face Pull", priority=55, fatigue=1, relevance="bench", pattern="scapular_control", equipment="cable"),
    exercise("Deficit Deadlift", priority=50, fatigue=5, relevance="deadlift", pattern="deadlift_off_floor", equipment="barbell"),
    exercise("Rack Pull", priority=45, fatigue=5, relevance="deadlift", pattern="deadlift_lockout", equipment="rack"),
    exercise("Pallof Press", priority=40, fatigue=1, pattern="trunk", equipment="cable"),
    exercise("Dumbbell Curl", priority=35, fatigue=1, pattern="elbow_flexion", equipment="dumbbell"),
)


@pytest.mark.parametrize("days", [
    ("SBD", "B", "SD"),                         # 3-day novice/intermediate
    ("SB", "D", "B", "SBD"),                  # 4-day standard PL
    ("SB", "D", "B", "S", "BD"),             # 5-day high bench
    ("B", "SD", "B", "B", "B", "SBD"),     # exact six-day philosophy
    ("B", "S", "D", "B", "S", "B", "SBD"),# 7-day edge case
])
def test_realistic_weekly_goldens_are_deterministic_distributed_and_nonredundant(days):
    context = WeeklyAccessoryContext(
        goal="development", volume="medium", week_count=4, day_types=days,
        available_equipment=frozenset({"barbell", "machine", "dumbbell", "cable", "rack"}),
    )
    planner = WeeklyAccessoryPlanner()
    first = planner.plan(GOLDEN_LIBRARY, context)
    second = planner.plan(reversed(GOLDEN_LIBRARY), context)

    assert [(x.exercise.name, x.day_index) for x in first] == [(x.exercise.name, x.day_index) for x in second]
    assert all(item.purpose in PURPOSES and item.reason for item in first)
    assert len({item.exercise.name for item in first}) == len(first)
    assert len({(item.exercise.swap_group, item.purpose) for item in first}) == len(first)
    assert all(len({item.purpose for item in first if item.day_index == day}) == len([item for item in first if item.day_index == day]) for day in range(len(days)))
    assert all(1 <= rx.sets <= 4 and 5 <= rx.rpe <= 9 and rx.rest_seconds >= 60 for item in first for rx in item.prescriptions)


def test_quality_state_and_equipment_gates_exclude_novel_disabled_and_conflicting_rows():
    candidates = [
        *GOLDEN_LIBRARY,
        exercise("Atlas Stone Carry", priority=999, fatigue=1, category="strongman"),
        exercise("Random Burpee Complex", priority=998, fatigue=1),
        exercise("Disabled Wonder Row", priority=997, fatigue=1, auto=False),
        exercise("Shoulder-Irritating Press", priority=996, fatigue=2, relevance="bench", constraints=("shoulder_loading",)),
    ]
    context = WeeklyAccessoryContext(
        goal="development", volume="high", week_count=3,
        day_types=("SB", "D", "B", "SBD"),
        constraints=frozenset({"shoulder_loading"}),
        available_equipment=frozenset({"barbell"}), readiness_multiplier=.7,
    )
    result = WeeklyAccessoryPlanner().plan(candidates, context)
    names = {item.exercise.name for item in result}
    assert not names & {"Atlas Stone Carry", "Random Burpee Complex", "Disabled Wonder Row", "Shoulder-Irritating Press"}
    assert all(item.exercise.equipment == "barbell" for item in result)


def test_high_bench_and_low_back_constrained_goldens_control_local_fatigue():
    constrained = replace(
        WeeklyAccessoryContext(
            goal="strength", volume="medium", week_count=3,
            day_types=("B", "SD", "B", "B", "B", "SBD"),
        ),
        constraints=frozenset({"shoulder_loading", "elbow_loading", "spinal_loading"}),
        observations=frozenset({"upper-back stability"}), readiness_multiplier=.8,
    )
    result = WeeklyAccessoryPlanner().plan(GOLDEN_LIBRARY, constrained)
    assert sum(item.purpose == "triceps strength" for item in result) <= 1
    assert sum(item.purpose in {"hip extension", "posterior-chain hypertrophy", "deadlift off-floor", "deadlift lockout"} for item in result) <= 2
    assert all(not (item.purpose in {"hip extension", "posterior-chain hypertrophy"} and "D" in constrained.day_types[(item.day_index + 1) % 6]) for item in result)


def test_meet_proximal_week_persists_a_real_taper_not_a_static_copy():
    context = WeeklyAccessoryContext(
        goal="peaking", volume="medium", week_count=4,
        day_types=("SB", "D", "B", "SBD"), meet_date=date.today() + timedelta(days=28),
    )
    result = WeeklyAccessoryPlanner().plan(GOLDEN_LIBRARY, context)
    assert result
    for item in result:
        assert item.prescriptions[-1].sets < item.prescriptions[0].sets or item.prescriptions[-1].sets == 1
        assert item.prescriptions[-1].rpe <= 7
        assert len({(rx.sets, rx.rpe) for rx in item.prescriptions}) > 1


def test_required_grip_respects_state_ranking_before_catalogue_priority():
    catalogue_favourite = exercise(
        "Hook Grip Hold A", priority=90, fatigue=1, relevance="deadlift",
        pattern="grip_a", category="grip",
    )
    state_favourite = exercise(
        "Hook Grip Hold B", priority=10, fatigue=1, relevance="deadlift",
        pattern="grip_b", category="grip",
    )
    result = WeeklyAccessoryPlanner().plan(
        (
            WeeklyAccessoryCandidate(catalogue_favourite),
            WeeklyAccessoryCandidate(
                state_favourite,
                state_score=20,
                state_provenance=({"rule_id": "coach.grip-preference.v1"},),
            ),
        ),
        WeeklyAccessoryContext(
            goal="development", volume="low", week_count=1,
            day_types=("D",), competition_grip="hook",
        ),
    )

    assert result[0].exercise.name == "Hook Grip Hold B"
    assert result[0].state_score == 20
    assert result[0].state_provenance == (
        {"rule_id": "coach.grip-preference.v1"},
    )


def test_volume_is_a_weekly_set_and_fatigue_policy_not_a_name_quota():
    planner = WeeklyAccessoryPlanner()
    totals = {}
    for volume in ("low", "medium", "high"):
        result = planner.plan(GOLDEN_LIBRARY, WeeklyAccessoryContext(
            goal="development", volume=volume, week_count=1,
            day_types=("SBD", "B", "SD"),
        ))
        totals[volume] = sum(item.prescriptions[0].sets for item in result)
        assert totals[volume] <= {"low": 6, "medium": 12, "high": 18}[volume]
        assert all(sum(
            candidate.prescriptions[0].sets for candidate in result
            if candidate.day_index == day
        ) <= 8 for day in range(3))
    assert totals["low"] < totals["medium"] <= totals["high"]


def test_reduced_readiness_changes_sets_rpe_count_and_supported_preference():
    healthy = WeeklyAccessoryContext(
        goal="development", volume="high", week_count=1,
        day_types=("SB", "D", "B", "S", "BD"), readiness_multiplier=1.0,
    )
    fatigued = replace(healthy, readiness_multiplier=.7)
    planner = WeeklyAccessoryPlanner()
    normal = planner.plan(GOLDEN_LIBRARY, healthy)
    reduced = planner.plan(GOLDEN_LIBRARY, fatigued)
    assert len(reduced) < len(normal)
    assert sum(x.prescriptions[0].sets for x in reduced) < sum(
        x.prescriptions[0].sets for x in normal
    )
    shared = {x.exercise.name: x for x in normal}.keys() & {
        x.exercise.name: x for x in reduced
    }.keys()
    assert shared
    assert all(
        next(x for x in reduced if x.exercise.name == name).prescriptions[0].rpe
        < next(x for x in normal if x.exercise.name == name).prescriptions[0].rpe
        for name in shared
    )


def test_meet_taper_reduces_movement_count_not_only_dose():
    base = WeeklyAccessoryContext(
        goal="strength", volume="high", week_count=1,
        day_types=("SB", "D", "B", "SBD"),
    )
    planner = WeeklyAccessoryPlanner()
    normal = planner.plan(GOLDEN_LIBRARY, base)
    taper = planner.plan(GOLDEN_LIBRARY, replace(
        base, goal="peaking", meet_date=date.today() + timedelta(days=10)
    ))
    assert len(taper) < len(normal)
    assert sum(x.prescriptions[0].sets for x in taper) < sum(
        x.prescriptions[0].sets for x in normal
    )
    assert all(x.prescriptions[0].rpe <= 7 for x in taper)


def test_structured_constraint_backstop_changes_selection_without_symptom_parsing():
    rows = (
        exercise("Barbell Good Morning", priority=100, fatigue=4,
                 relevance="deadlift", pattern="hinge"),
        exercise("JM Press", priority=99, fatigue=3, relevance="bench",
                 pattern="elbow_extension"),
        exercise("Chest-Supported Row", priority=20, fatigue=2,
                 relevance="bench", pattern="horizontal_pull"),
        exercise("Lying Leg Curl", priority=19, fatigue=2,
                 relevance="deadlift", pattern="knee_flexion"),
    )
    base = WeeklyAccessoryContext(
        goal="development", volume="high", week_count=1,
        day_types=("SB", "D", "B"),
    )
    planner = WeeklyAccessoryPlanner()
    unconstrained = {x.exercise.name for x in planner.plan(rows, base)}
    constrained = {x.exercise.name for x in planner.plan(rows, replace(
        base, constraints=frozenset({"shoulder_loading", "spinal_loading"})
    ))}
    assert {"Barbell Good Morning", "JM Press"} <= unconstrained
    assert not constrained & {"Barbell Good Morning", "JM Press"}
    assert constrained & {"Chest-Supported Row", "Lying Leg Curl"}


def test_session_ledger_prevents_multiple_high_fatigue_lower_compounds():
    result = WeeklyAccessoryPlanner().plan(GOLDEN_LIBRARY, WeeklyAccessoryContext(
        goal="development", volume="high", week_count=1,
        day_types=("B", "D", "S"), available_equipment=frozenset({"barbell", "rack"}),
    ))
    demanding_lower = {
        "Paused High-Bar Squat", "Barbell Hip Thrust", "Deficit Deadlift", "Rack Pull"
    }
    assert all(sum(
        item.exercise.name in demanding_lower for item in result
        if item.day_index == day
    ) <= 1 for day in range(3))
