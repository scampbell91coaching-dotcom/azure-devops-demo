from dataclasses import replace
from datetime import date, timedelta

from portal.models.exercise_library import Exercise
from portal.services.weekly_accessory_planner import (
    AccessoryHistory, WeeklyAccessoryContext, WeeklyAccessoryPlanner,
)


def row(identity, name, purpose, *, priority=10, fatigue=2, pattern=None,
        group=None, tags=(), constraints=(), sets=None, reps=None, auto=True):
    purposes = [purpose, *tags] if purpose else list(tags)
    return Exercise(
        id=identity, name=name, movement="accessory", category="assistance",
        active=True, accessory_suitable=True, auto_select=auto,
        coach_priority=priority, fatigue_rating=fatigue,
        technical_purposes=str(purposes).replace("'", '"'),
        compatibility_tags=str(list(tags)).replace("'", '"'),
        constraint_tags=str(list(constraints)).replace("'", '"'),
        movement_pattern=pattern, swap_group=group,
        default_sets=sets, default_reps=reps,
    )


LIBRARY = (
    row(1, "Leg Press", "quad strength", priority=30, group="quad"),
    row(2, "Supported Row", "upper-back stability", priority=20, group="row", tags=("stable",)),
    row(3, "Triceps", "triceps strength", priority=18, group="triceps"),
    row(4, "Curl", "general hypertrophy", priority=15, group="curl"),
    row(5, "Rear Delt", "bench stability", priority=14, group="rear-delt"),
    row(6, "Leg Curl", "posterior-chain hypertrophy", priority=13, group="hamstring"),
    row(7, "Core", "low-fatigue technical support", priority=12, group="core", fatigue=1),
    row(8, "Pec Machine", "bench pec strength", priority=11, group="pec", tags=("stable",)),
)


def context(days=("SBD", "B", "D"), **kwargs):
    return WeeklyAccessoryContext("development", "high", 4, days, **kwargs)


def test_planning_is_weekly_sbd_restrained_and_bench_led_can_carry_more():
    result = WeeklyAccessoryPlanner().plan(LIBRARY, context())
    counts = [sum(item.day_index == day for item in result) for day in range(3)]
    assert len(result) > max(counts)
    assert counts[0] <= 2
    assert counts[1] >= counts[0]


def test_weak_point_priority_is_additive_to_general_development():
    result = WeeklyAccessoryPlanner().plan(
        LIBRARY, context(weak_point_priorities=frozenset({"quad strength"}))
    )
    purposes = {item.purpose for item in result}
    assert "quad strength" in purposes
    assert purposes & {"general hypertrophy", "upper-back stability", "bench stability"}


def test_new_accessory_starts_at_two_sets_without_universal_progression():
    item = WeeklyAccessoryPlanner().plan((LIBRARY[3],), context(days=("B",)))[0]
    assert [week.sets for week in item.prescriptions] == [2, 2, 2, 2]
    assert [week.reps for week in item.prescriptions] == ["10-15"] * 4


def test_successful_continuity_wins_and_pain_forces_substitution():
    old = row(20, "Old Row", "upper-back stability", priority=1, group="row")
    new = row(21, "New Row", "upper-back stability", priority=99, group="row")
    planner = WeeklyAccessoryPlanner()
    kept = planner.plan((old, new), context(history=(AccessoryHistory(20),)))
    assert [item.exercise.id for item in kept] == [20]
    swapped = planner.plan((old, new), context(history=(AccessoryHistory(20, pain=True),)))
    assert [item.exercise.id for item in swapped] == [21]


def test_priority_is_ordered_earlier_within_session():
    result = WeeklyAccessoryPlanner().plan(
        LIBRARY, context(days=("B",), weak_point_priorities=frozenset({"triceps strength"}))
    )
    assert result[0].purpose == "triceps strength"


def test_stable_regression_preferred_when_skill_exceeds_capacity():
    unsupported = row(30, "Unsupported Single-leg RDL", "coordination/control",
                      priority=99, group="single-leg", tags=("high_skill",))
    supported = row(31, "Wall-supported Single-leg RDL", "coordination/control",
                    priority=20, group="single-leg", tags=("stable",))
    result = WeeklyAccessoryPlanner().plan(
        (unsupported, supported), context(skill_capacity="limited",
                                        stability_requirement="maximal_local_stimulus")
    )
    assert result[0].exercise.id == 31


def test_heavy_split_squat_is_not_automatically_placed_after_sbd():
    split = row(40, "Heavy Split Squat", "quad strength", fatigue=5,
                pattern="split_squat", tags=("heavy_split_squat",))
    result = WeeklyAccessoryPlanner().plan((split,), context(days=("SBD", "B")))
    assert result and result[0].day_index == 1


def test_missing_semantics_disables_random_auto_selection():
    unknown = row(50, "Mystery", "", pattern="unknown")
    assert WeeklyAccessoryPlanner().plan((unknown,), context()) == ()


def test_coach_pin_is_preserved_even_without_semantics_or_auto_select():
    pin = row(60, "Coach Choice", "", auto=False)
    result = WeeklyAccessoryPlanner().place_pins((pin,), context())
    assert result[0].exercise.id == 60
    assert result[0].purpose == "coach-directed"


def test_extra_days_distribute_instead_of_increasing_weekly_work():
    planner = WeeklyAccessoryPlanner()
    four = planner.plan(LIBRARY, context(days=("B", "S", "D", "B")))
    six = planner.plan(LIBRARY, context(days=("B", "S", "D", "B", "S", "B")))
    assert {item.exercise.id for item in four} == {item.exercise.id for item in six}


def test_near_meet_reduces_work_but_retains_low_cost_support():
    planner = WeeklyAccessoryPlanner()
    normal = planner.plan(LIBRARY, context())
    taper = planner.plan(LIBRARY, replace(
        context(), goal="peaking", meet_date=date.today() + timedelta(days=10)
    ))
    assert len(taper) < len(normal)
    assert any(item.purpose == "low-fatigue technical support" for item in taper)
