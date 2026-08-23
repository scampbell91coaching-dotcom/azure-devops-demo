import pytest

from portal.services.exposure_intelligence import weekly_exposure_intents


def _flat(sequence):
    return [item for day in weekly_exposure_intents(
        sequence, goal="strength", deadlift_style="conventional"
    ) for item in day]


@pytest.mark.parametrize("frequency", [5, 6])
def test_high_frequency_bench_has_exactly_two_distinct_hard_competition_exposures(frequency):
    bench = [item for item in _flat(["B"] * frequency) if item.lift_family == "bench"]
    hard = [item for item in bench if item.stress_role == "hard"]
    assert len(hard) == 2
    assert {item.purpose for item in hard} == {
        "competition_intensity", "competition_volume",
    }
    assert {item.exercise_name for item in hard} == {"Competition Bench Press"}
    assert all(item.stress_role == "lower_stress" for item in bench if item not in hard)


def test_sbd_primary_uses_sbd_and_earliest_other_suitable_bench_as_hard():
    days = weekly_exposure_intents(
        ["B", "B", "SBD"], goal="strength", deadlift_style="conventional"
    )
    assert days[2][1].purpose == "competition_intensity"
    assert days[0][0].purpose == "competition_volume"


def test_non_primary_sbd_uses_latest_suitable_bench_before_sbd():
    days = weekly_exposure_intents(
        ["B", "B", "DBS"], goal="strength", deadlift_style="conventional"
    )
    assert days[0][0].purpose == "competition_intensity"
    assert days[1][0].purpose == "competition_volume"
    assert days[2][1].stress_role == "lower_stress"
    assert all(
        item.purpose != "competition_intensity"
        for item in days[2] if item.lift_family == "bench"
    )


def test_primary_bench_is_never_after_deadlift():
    with pytest.raises(ValueError, match="valid primary placement"):
        weekly_exposure_intents(["DB"], goal="strength", deadlift_style="conventional")


def test_secondary_lower_lifts_have_explicit_purpose_and_deadlift_is_capped():
    exposures = _flat(["SD", "SBD"])
    secondary = [item for item in exposures
                 if item.lift_family in {"squat", "deadlift"}
                 and item.stress_role == "secondary"]
    assert {item.lift_family: item.purpose for item in secondary} == {
        "squat": "positional", "deadlift": "technical_secondary",
    }
    with pytest.raises(ValueError, match="cannot exceed two"):
        _flat(["D", "D", "D"])
