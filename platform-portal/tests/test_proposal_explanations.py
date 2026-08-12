from dataclasses import asdict
import json
from types import SimpleNamespace

from portal.services.proposal_explanations import ProposalExplanationService


def _context():
    return SimpleNamespace(
        state_facts={"sleep_note": "poor", "competition_date": "2026-10-01"},
        state_signals={"reported_fatigue": 4, "rpe_adherence_rate": 0.8},
        active_constraints=("limited session duration",),
        technical_observations=("squat: loses position",),
        active_overrides=(
            {
                "target_type": "programming",
                "target_ref": "goal",
                "override": {"goal": "strength"},
                "reason": "Competition preparation",
                "recorded_by": "coach@example.test",
            },
        ),
        missing=("weight class", "bodyweight"),
    )


def _build():
    return ProposalExplanationService().build(
        factory=SimpleNamespace(),
        weekly_structure=(
            {
                "exposures": ("Competition Squat", "Competition Bench Press"),
                "assistance": ("Cable Row",),
            },
            {"exposures": ("Conventional Deadlift",), "assistance": ()},
        ),
        context=_context(),
        rpe_values=(6.5, 7.0, 7.5),
        volume_values=(30, 30, 24),
        reference_block={
            "id": 12,
            "name": "Previous strength block",
            "exercises": ("Competition Squat", "Paused Bench Press"),
        },
        assistance_reasons={"Cable Row": ("Balances pressing volume",)},
    )


def test_proposal_explanation_is_deterministic_and_json_serialisable():
    first = json.dumps(asdict(_build()), sort_keys=True, separators=(",", ":"))
    second = json.dumps(asdict(_build()), sort_keys=True, separators=(",", ":"))

    assert first == second


def test_proposal_explanation_has_stable_reasons_and_evidence_backed_sections():
    explanation = _build()

    assert explanation.schema_version == "proposal-explanation-v1"
    assert explanation.reference_block.reason_id == "reference.latest-athlete-block"
    assert [item.id for item in explanation.kept] == [
        "kept-exposure:Competition Squat"
    ]
    assert [item.reason_id for item in explanation.changed] == [
        "diff.exposure-added",
        "diff.exposure-added",
        "diff.exposure-removed",
    ]
    assert explanation.assistance[0].reason == "Balances pressing volume"
    assert explanation.warm_ups[0].reason_id == "warmup.outside-generator-scope"
    assert [item.id for item in explanation.athlete_state_evidence] == [
        "athlete-state:fact:competition_date",
        "athlete-state:fact:sleep_note",
        "athlete-state:signal:reported_fatigue",
        "athlete-state:signal:rpe_adherence_rate",
        "athlete-state:constraint:1",
        "athlete-state:technical-observation:1",
    ]
    assert [item.label for item in explanation.warnings] == [
        "Missing bodyweight",
        "Missing weight class",
    ]
    assert explanation.coach_overrides[0].reason == "Competition preparation"


def test_proposal_explanation_makes_absent_reference_and_assistance_explicit():
    context = _context()
    context.active_overrides = ()
    context.missing = ()
    explanation = ProposalExplanationService().build(
        factory=SimpleNamespace(),
        weekly_structure=({"exposures": ("Competition Squat",), "assistance": ()},),
        context=context,
        rpe_values=(6.0,),
        volume_values=(12,),
    )

    assert explanation.reference_block.reason_id == "reference.none-available"
    assert explanation.assistance[0].reason_id == "assistance.none-selected"
    assert explanation.kept == ()
    assert explanation.coach_overrides == ()
    assert explanation.changed == ()
    assert explanation.warnings[0].reason_id == "warning.reference-missing"
