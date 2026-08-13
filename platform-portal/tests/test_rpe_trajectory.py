import pytest

from portal.programming_services.rpe_trajectory import (
    BlockType,
    CoachRpeOverride,
    IntensityPattern,
    RpeTrajectoryRequest,
    TrajectoryPolicy,
    build_rpe_trajectory,
)


def targets(curve):
    return [week.target_rpe for week in curve]


def test_accumulation_starts_conservatively_and_reaches_configured_endpoint():
    curve = build_rpe_trajectory(
        RpeTrajectoryRequest(
            block_type=BlockType.ACCUMULATION,
            block_length=5,
            target_rpe=8.5,
            target_week=4,
        )
    )

    assert targets(curve) == [7.0, 7.5, 8.0, 8.5, 8.5]
    assert curve[0].maximum_rpe < 10
    assert curve[3].phase == "target"
    assert curve[4].phase == "hold"


def test_strength_wave_uses_half_rpe_down_weeks():
    curve = build_rpe_trajectory(
        RpeTrajectoryRequest(
            block_type=BlockType.STRENGTH,
            block_length=5,
            target_rpe=9.0,
        )
    )

    assert targets(curve) == [7.5, 7.5, 8.5, 8.0, 9.0]
    assert curve[1].phase == "wave_down"


def test_peak_with_meet_context_reduces_fatigue_after_target_week():
    curve = build_rpe_trajectory(
        RpeTrajectoryRequest(
            block_type=BlockType.PEAK,
            block_length=6,
            target_rpe=9.0,
            target_week=4,
            meet_context=True,
        )
    )

    assert targets(curve) == [7.5, 8.0, 8.5, 9.0, 8.0, 7.0]
    assert curve[4].phase == curve[5].phase == "fatigue_reduction"


def test_taper_defaults_to_falling_curve_instead_of_climbing():
    curve = build_rpe_trajectory(
        RpeTrajectoryRequest(
            block_type=BlockType.TAPER,
            block_length=3,
            target_rpe=8.0,
        )
    )

    assert targets(curve) == [8.0, 7.0, 6.0]


def test_rebuild_holds_below_its_separate_guardrail():
    curve = build_rpe_trajectory(
        RpeTrajectoryRequest(
            block_type=BlockType.REBUILD_REHAB,
            block_length=3,
            target_rpe=9.5,
        )
    )

    assert targets(curve) == [7.0, 7.0, 7.0]
    assert all(week.maximum_rpe <= 8.0 for week in curve)


def test_custom_requires_and_applies_an_explicit_pattern():
    with pytest.raises(ValueError, match="custom blocks require"):
        build_rpe_trajectory(
            RpeTrajectoryRequest(BlockType.CUSTOM, block_length=3, target_rpe=8.0)
        )

    curve = build_rpe_trajectory(
        RpeTrajectoryRequest(
            BlockType.CUSTOM,
            block_length=3,
            target_rpe=8.0,
            pattern=IntensityPattern.HOLD,
        )
    )
    assert targets(curve) == [6.5, 6.5, 6.5]


def test_normal_guardrail_prevents_rpe_ten_but_audited_override_can_request_it():
    curve = build_rpe_trajectory(
        RpeTrajectoryRequest(
            block_type=BlockType.STRENGTH,
            block_length=3,
            target_rpe=10.0,
            overrides=(
                CoachRpeOverride(
                    week=3,
                    target_rpe=10.0,
                    minimum_rpe=9.5,
                    maximum_rpe=10.0,
                    coach_id="coach-42",
                    reason="Observed meet-day readiness and approved final single",
                ),
            ),
        )
    )

    assert targets(curve) == [7.5, 8.0, 10.0]
    assert curve[2].phase == "coach_override"
    assert curve[2].override is not None
    assert curve[2].override.coach_id == "coach-42"
    assert "meet-day readiness" in curve[2].explanation


def test_policy_is_injectable_instead_of_baking_example_values_into_algorithm():
    curve = build_rpe_trajectory(
        RpeTrajectoryRequest(BlockType.ACCUMULATION, 3, target_rpe=8.0),
        policy=TrajectoryPolicy(
            conservative_start_gap=1.0,
            envelope_half_width=0.0,
            normal_maximum_rpe=8.5,
        ),
    )

    assert targets(curve) == [7.0, 7.5, 8.0]
    assert all(week.minimum_rpe == week.maximum_rpe for week in curve)


@pytest.mark.parametrize(
    ("trajectory_request", "message"),
    [
        (RpeTrajectoryRequest(BlockType.STRENGTH, 0, 8.0), "block_length"),
        (RpeTrajectoryRequest(BlockType.STRENGTH, 3, 8.0, target_week=4), "target_week"),
        (RpeTrajectoryRequest(BlockType.STRENGTH, 3, 10.5), "target_rpe"),
    ],
)
def test_invalid_trajectory_configuration_is_rejected(trajectory_request, message):
    with pytest.raises(ValueError, match=message):
        build_rpe_trajectory(trajectory_request)


def test_override_requires_auditable_identity_and_reason():
    request = RpeTrajectoryRequest(
        BlockType.PEAK,
        2,
        9.0,
        overrides=(CoachRpeOverride(2, 9.5, coach_id="", reason=""),),
    )
    with pytest.raises(ValueError, match="coach_id and reason"):
        build_rpe_trajectory(request)
