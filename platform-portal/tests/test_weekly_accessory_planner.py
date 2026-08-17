"""Realistic golden programmes for Traditional Strength Accessory Intelligence V2."""

from dataclasses import replace
from datetime import date, timedelta

import pytest

from portal.models.exercise_library import Exercise
from portal.services.weekly_accessory_planner import (
    PURPOSES, WeeklyAccessoryContext, WeeklyAccessoryPlanner,
)


def exercise(name, *, priority, fatigue, relevance="all", pattern=None,
             equipment=None, constraints=(), auto=True, category="assistance",
             sets=None, reps=None, rpe=None, rest=None):
    return Exercise(
        id=priority, name=name, movement="accessory", category=category,
        active=True, accessory_suitable=True, auto_select=auto,
        coach_priority=priority, fatigue_rating=fatigue,
        lift_relevance=f'["{relevance}"]', movement_pattern=pattern,
        swap_group=f"golden:{pattern}" if pattern else None,
        equipment=equipment,
        equipment_options=f'["{equipment}"]' if equipment else None,
        constraint_tags=str(list(constraints)).replace("'", '"'),
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
