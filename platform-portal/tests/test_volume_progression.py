from datetime import date

import pytest

from portal.services.volume_progression import (
    ReferenceVolume,
    VolumeProgressionService,
)


def proposal(block_type, rpe, **kwargs):
    return VolumeProgressionService().propose(
        block_type=block_type,
        duration=len(rpe),
        rpe_curve=rpe,
        training_days=4,
        frequencies={"squat": 2, "bench": 3, "deadlift": 1},
        **kwargs,
    )


def test_accumulation_carries_more_volume_without_chasing_rpe():
    result = proposal("accumulation", [6.0, 7.0, 8.0, 8.5])

    assert result.weeks[0].sbd_sets == {"squat": 7, "bench": 11, "deadlift": 4}
    assert result.weeks[-1].sbd_sets["squat"] <= result.weeks[-2].sbd_sets["squat"]
    assert result.weeks[-1].assistance_fatigue_budget <= result.weeks[0].assistance_fatigue_budget


def test_strength_volume_recedes_as_rpe_climbs():
    result = proposal("strength", [6.5, 7.5, 8.5, 8.5])

    squat = [week.sbd_sets["squat"] for week in result.weeks]
    assert squat == sorted(squat, reverse=True)
    assert result.weeks[-1].sbd_sets["bench"] < result.weeks[0].sbd_sets["bench"]


def test_peak_with_meet_context_finishes_in_meaningful_taper():
    result = proposal(
        "peak", [7.0, 8.0, 8.5, 9.0], meet_date=date(2026, 10, 24)
    )

    peak, taper = result.weeks[-2:]
    assert taper.phase == "taper"
    assert taper.sbd_sets == {"squat": 2, "bench": 3, "deadlift": 1}
    assert taper.assistance_fatigue_budget <= peak.assistance_fatigue_budget // 2
    assert "fatigue-reducing taper" in " ".join(result.explanation)


def test_standalone_taper_preserves_exposures_and_separates_assistance():
    result = proposal("taper", [6.0, 6.5])

    for week in result.weeks:
        assert week.sbd_sets == {"squat": 2, "bench": 3, "deadlift": 1}
        assert week.assistance_fatigue_budget < sum(week.sbd_sets.values())


def test_reference_baseline_and_explained_coach_overrides_are_reviewable():
    result = proposal(
        "accumulation",
        [6.0, 7.0],
        reference=ReferenceVolume(
            {"squat": 10, "bench": 14, "deadlift": 5}, 20, "Prior block"
        ),
        constraints=("limited session duration",),
        overrides=(
            {
                "override": {
                    "weekly_sbd_sets": {"deadlift": 3},
                    "assistance_fatigue_budget": 8,
                },
                "reason": "Coach recovery decision",
            },
        ),
    )

    assert result.weeks[0].sbd_sets["deadlift"] == 3
    assert result.weeks[0].assistance_fatigue_budget == 8
    assert any("Prior block" in reason for reason in result.explanation)
    assert any("Coach recovery decision" in item for item in result.overrides_applied)
    assert result.weeks[0].sbd_range["squat"][1] == result.weeks[0].sbd_sets["squat"]


@pytest.mark.parametrize("bad_curve", ([7.0], [0.0, 7.0], [7.0, 11.0]))
def test_invalid_rpe_curve_is_rejected(bad_curve):
    with pytest.raises(ValueError):
        VolumeProgressionService().propose(
            block_type="strength",
            duration=2,
            rpe_curve=bad_curve,
            training_days=3,
            frequencies={"squat": 1, "bench": 1, "deadlift": 1},
        )
