import pytest

from portal.services.exposure_intelligence import weekly_exposure_intents
from portal.services.weekly_planner import SECONDARY_LOWER_PURPOSES, WeeklyPlanner


def plan(days, squat, bench, deadlift):
    return WeeklyPlanner().plan(
        training_days=days, squat_frequency=squat,
        bench_frequency=bench, deadlift_frequency=deadlift,
    )


def counts(structure):
    return {code: sum(code in day for day in structure.day_sequence) for code in "SBD"}


def test_canonical_six_day_structure_and_five_bench_exposures():
    structure = plan(6, 2, 5, 2)
    assert structure.day_sequence == ["B", "SD", "B", "B", "B", "SBD"]
    assert counts(structure) == {"S": 2, "B": 5, "D": 2}


def test_six_day_structure_supports_six_bench_without_adding_lower_exposures():
    structure = plan(6, 2, 6, 2)
    assert structure.day_sequence == ["B", "SBD", "B", "B", "B", "SBD"]
    assert counts(structure) == {"S": 2, "B": 6, "D": 2}


@pytest.mark.parametrize("bench", [5, 6])
def test_high_frequency_skeleton_retains_exactly_two_hard_benches(bench):
    structure = plan(6, 2, bench, 2)
    intents = [item for day in weekly_exposure_intents(
        structure, goal="strength", deadlift_style="conventional"
    ) for item in day if item.lift_family == "bench"]
    assert len([item for item in intents if item.stress_role == "hard"]) == 2


@pytest.mark.parametrize(
    ("days", "expected"),
    [(3, ["BD", "SB", "SB"]),
     (4, ["B", "S", "BD", "SB"]),
     (5, ["B", "S", "B", "D", "SB"])],
)
def test_three_four_five_day_goldens_are_distributed_and_deterministic(days, expected):
    first = plan(days, 2, 3, 1)
    assert first.day_sequence == expected
    assert first == plan(days, 2, 3, 1)
    assert counts(first) == {"S": 2, "B": 3, "D": 1}
    assert all(day != "SBD" for day in first.day_sequence)
    assert all(day.index("S") < day.index("B") if "S" in day and "B" in day else True
               for day in first.day_sequence)
    assert all(day.index("B") < day.index("D") if "B" in day and "D" in day else True
               for day in first.day_sequence)


def test_ordering_caps_and_secondary_lower_purpose():
    structure = plan(6, 2, 5, 2)
    assert structure.day_sequence[-1] == "SBD"
    assert structure.day_sequence[1] == "SD"
    secondary = [item for day in structure.days for item in day.exposures
                 if item.lift_family in {"squat", "deadlift"} and item.placement == "secondary"]
    assert secondary
    assert all(item.purpose in SECONDARY_LOWER_PURPOSES for item in secondary)
    with pytest.raises(ValueError, match="Deadlift cannot exceed|deadlift cannot exceed"):
        plan(4, 1, 1, 3)
    with pytest.raises(ValueError, match="squat cannot exceed"):
        plan(4, 3, 1, 1)


def test_more_days_distribute_requested_work_not_create_hard_work():
    four = weekly_exposure_intents(plan(4, 2, 3, 1), goal="strength", deadlift_style="conventional")
    five = weekly_exposure_intents(plan(5, 2, 3, 1), goal="strength", deadlift_style="conventional")
    hard = lambda result: sum(item.stress_role == "hard" for day in result for item in day)
    assert hard(four) == hard(five) == 2
