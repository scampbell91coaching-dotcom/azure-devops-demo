import pytest

from portal.services.prescription_planner import PrescriptionContext, PrescriptionPlanner
from portal.services.variation_selector import (
    CoachSelectionRequired, VariationContext, VariationSelector,
)


def selection(family, purpose, role="secondary", **values):
    return VariationSelector().select(VariationContext(
        lift_family=family, purpose=purpose, stress_role=role, **values
    ))


@pytest.mark.parametrize("purpose", ["competition_intensity", "competition_volume"])
def test_hard_bench_is_competition_bench(purpose):
    result = selection("bench", purpose, "hard")
    assert result.exercise_name == "Competition Bench Press"
    assert "competition" in result.reason.casefold()


def test_lower_stress_bench_choices_are_problem_led():
    assert selection("bench", "technical", "lower_stress").exercise_name == "Paused Bench Press"
    assert selection("bench", "positional", "lower_stress").exercise_name == "Spoto Press"
    assert selection("bench", "development", "lower_stress").exercise_name == "Larsen Press"
    assert selection("bench", "technical", "lower_stress").exercise_name != "Incline Bench Press"


def test_known_lower_variations_follow_purpose():
    assert selection("deadlift", "technical_secondary").exercise_name == "Paused Deadlift"
    assert selection("deadlift", "capacity_hypertrophy").exercise_name == "Romanian Deadlift"
    assert selection("deadlift", "lower_cost").exercise_name == "Romanian Deadlift"
    assert selection("squat", "positional").exercise_name == "Pause Squat"


def test_selection_is_deterministic_and_pin_is_authoritative():
    context = VariationContext("bench", "positional", "lower_stress")
    assert VariationSelector().select(context) == VariationSelector().select(context)
    pinned = selection("bench", "positional", "lower_stress",
                       coach_pinned_exercise="Coach Custom Bench")
    assert (pinned.exercise_name, pinned.provenance) == ("Coach Custom Bench", "coach_selected")


def test_unsupported_does_not_randomly_choose_when_competition_is_incompatible():
    with pytest.raises(CoachSelectionRequired, match="Coach selection required"):
        selection("bench", "unsupported_specialism", pain_or_tolerance=("bench",))


def test_beginner_avoids_unnecessary_specialist_variation():
    result = selection("bench", "development", "lower_stress", athlete_level="beginner")
    assert result.exercise_name == "Competition Bench Press"


def prescription(purpose, role, *, phase="strength", sets=4, rpe=8.0, structure=None):
    return PrescriptionPlanner().plan(PrescriptionContext(
        purpose=purpose, stress_role=role, phase=phase, week=1, week_count=4,
        target_rpe=rpe, allocated_sets=sets, structure_preference=structure,
    ))


def test_hard_intensity_and_volume_differ_by_intent_and_straight_sets_work():
    intensity = prescription("competition_intensity", "hard")
    volume = prescription("competition_volume", "hard")
    assert intensity.structure == volume.structure == "straight_sets"
    assert intensity.components[0].reps != volume.components[0].reps
    assert intensity.components[0].rpe > volume.components[0].rpe


def test_top_set_and_backoffs_are_supported():
    result = prescription("competition_intensity", "hard", structure="top_set_backoffs")
    assert result.structure == "top_set_backoffs"
    assert [item.role for item in result.components] == ["top_set", "backoff"]
    assert result.components[0].rpe > result.components[1].rpe


def test_lower_stress_bench_stays_below_hard_work():
    lower = prescription("technical", "lower_stress")
    hard = prescription("competition_intensity", "hard")
    assert 2 <= lower.sets <= 3
    assert lower.components[0].rpe <= 7.0 < hard.components[0].rpe


def test_secondary_lower_dose_depends_on_purpose():
    technical = prescription("technical_secondary", "secondary", sets=3)
    capacity = prescription("capacity_hypertrophy", "secondary", sets=4)
    low_cost = prescription("lower_cost", "secondary", sets=2)
    assert len({item.components[0].reps for item in (technical, capacity, low_cost)}) == 3
    assert capacity.components[0].rpe > low_cost.components[0].rpe


def test_near_meet_increases_specificity_without_making_everything_harder():
    normal_hard = prescription("competition_intensity", "hard")
    meet_hard = prescription("competition_intensity", "hard", phase="peaking")
    normal_lower = prescription("technical", "lower_stress")
    meet_lower = prescription("technical", "lower_stress", phase="peaking")
    assert meet_hard.components[0].reps == "1"
    assert meet_lower.components[0].rpe <= normal_lower.components[0].rpe
    assert meet_hard.components[0].rpe == normal_hard.components[0].rpe
