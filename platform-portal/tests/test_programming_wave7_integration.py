"""Wave 7 coaching-intent goldens and final integration gate.

These goldens deliberately assert stable coaching decisions rather than every
display field or incidental numeric value in a serialized preview.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pytest

from portal.models.exercise_library import Exercise
from portal.services.adaptation_policy import AdaptationEvidence, ConservativeAdaptationPolicy
from portal.services.exposure_intelligence import weekly_exposure_intents
from portal.services.golden_programmes import golden_programmes
from portal.services.prescription_planner import PrescriptionContext, PrescriptionPlanner
from portal.services.variation_selector import VariationContext, VariationSelector
from portal.services.weekly_accessory_planner import WeeklyAccessoryContext, WeeklyAccessoryPlanner
from portal.services.weekly_planner import WeeklyPlanner


GOLDENS = [
    *(
        {
            "name": item["name"], "kind": "structure",
            "days": item["training_days"], "squat": item["squat_frequency"],
            "bench": item["bench_frequency"], "deadlift": item["deadlift_frequency"],
            "expected": item["expected"],
        }
        for item in golden_programmes()
    ),
    *(
        item for item in json.loads(
            (Path(__file__).parent / "fixtures/wave7_coaching_goldens.json").read_text()
        ) if item["kind"] != "structure"
    ),
]


def _intents(sequence):
    return weekly_exposure_intents(sequence, goal="strength", deadlift_style="conventional")


def _accessory(identity, name, purpose, priority):
    return Exercise(id=identity, name=name, movement="accessory", category="assistance",
                    active=True, accessory_suitable=True, auto_select=True,
                    coach_priority=priority, fatigue_rating=2,
                    movement_pattern="elbow_flexion",
                    technical_purposes=json.dumps([purpose]), swap_group=name)


@pytest.mark.parametrize("golden", GOLDENS, ids=lambda item: item["name"])
def test_representative_coaching_goldens(golden):
    kind = golden["kind"]
    if kind == "structure":
        result = WeeklyPlanner().plan(
            training_days=golden["days"], squat_frequency=golden["squat"],
            bench_frequency=golden["bench"], deadlift_frequency=golden["deadlift"],
        )
        assert result.day_sequence == golden["expected"]
        assert all(day.sequence_code == "".join(
            code for code in "SBD" if code in day.sequence_code
        ) for day in result.days)
        return

    if kind in {"bench", "bench-placement"}:
        planned = _intents(golden["sequence"])
        bench = [(day, item) for day, values in enumerate(planned) for item in values
                 if item.lift_family == "bench"]
        hard = [(day, item) for day, item in bench if item.stress_role == "hard"]
        assert len(bench) == golden.get("frequency", len(bench))
        assert {item.purpose for _, item in hard} == {
            "competition_intensity", "competition_volume"
        }
        assert all(item.exercise_name == "Competition Bench Press" for _, item in hard)
        assert all(item.stress_role == "lower_stress" for pair in bench if pair not in hard
                   for item in [pair[1]])
        if kind == "bench-placement":
            by_purpose = {item.purpose: day for day, item in hard}
            assert by_purpose["competition_intensity"] == golden["intensity_day"]
            assert by_purpose["competition_volume"] == golden["volume_day"]
        return

    if kind == "secondary":
        secondary = next(item for day in _intents(golden["sequence"]) for item in day
                         if item.lift_family == golden["family"] and
                         item.stress_role == "secondary")
        selection = VariationSelector().select(VariationContext(
            secondary.lift_family, secondary.purpose, secondary.stress_role
        ))
        assert (secondary.purpose, selection.exercise_name) == (
            golden["purpose"], golden["exercise"]
        )
        return

    library = (
        _accessory(1, "Priority Triceps", "triceps strength", 30),
        _accessory(2, "General Curl", "general hypertrophy", 20),
        _accessory(3, "Supported Row", "upper-back stability", 10),
    )
    context = WeeklyAccessoryContext("hypertrophy", "medium", 4, ("B", "S", "D", "B"))
    if kind == "accessory":
        if golden["intent"] == "weak-point":
            context = replace(context, weak_point_priorities=frozenset({"triceps strength"}))
        result = WeeklyAccessoryPlanner().plan(library, context)
        purposes = {item.purpose for item in result}
        assert "general hypertrophy" in purposes
        assert purposes & {"upper-back stability", "triceps strength"}
        if golden["intent"] == "weak-point":
            assert result[0].purpose == "triceps strength"
        return

    if kind == "meet":
        normal = WeeklyAccessoryPlanner().plan(library, context)
        near = WeeklyAccessoryPlanner().plan(library, replace(
            context, goal="peaking", meet_date=date.today() + timedelta(days=10)
        ))
        prescription = PrescriptionPlanner().plan(PrescriptionContext(
            "competition_intensity", "hard", "peaking", 1, 2, 8.0, 3
        ))
        assert prescription.components[0].reps == "1"
        assert sum(item.sets for planned in near for item in planned.prescriptions) < sum(
            item.sets for planned in normal for item in planned.prescriptions
        )
        return

    if kind == "adaptation":
        evidence = AdaptationEvidence("rpe_drift", 1.5, "week-1", ("session:1",), "bench")
        result = ConservativeAdaptationPolicy().evaluate([evidence])
        assert result.decision == "maintain" and result.adjustment is None
        return

    raise AssertionError(f"Unhandled golden kind: {kind}")


def test_release_invariants_reject_unsupported_workload_and_selection():
    planner = WeeklyPlanner()
    with pytest.raises(ValueError, match="deadlift cannot exceed"):
        planner.plan(training_days=4, squat_frequency=1, bench_frequency=1,
                     deadlift_frequency=3)
    with pytest.raises(ValueError, match="squat cannot exceed"):
        planner.plan(training_days=4, squat_frequency=3, bench_frequency=1,
                     deadlift_frequency=1)
    fallback = VariationSelector().select(VariationContext(
        "squat", "unsupported_generic_default", "secondary"
    ))
    assert (fallback.exercise_name, fallback.provenance) == (
        "Competition Squat", "competition_fallback"
    )


def test_more_days_do_not_invent_hard_or_accessory_work_and_no_generic_progression():
    planner = WeeklyPlanner()
    hard_counts = []
    for days in (4, 5):
        structure = planner.plan(training_days=days, squat_frequency=2,
                                 bench_frequency=3, deadlift_frequency=1)
        hard_counts.append(sum(item.stress_role == "hard" for day in _intents(structure)
                               for item in day))
    assert hard_counts == [2, 2]

    exercise = _accessory(10, "Unprogressed Curl", "general hypertrophy", 10)
    accessory = WeeklyAccessoryPlanner().plan((exercise,), WeeklyAccessoryContext(
        "hypertrophy", "medium", 4, ("B",)
    ))[0]
    assert [item.sets for item in accessory.prescriptions] == [2, 2, 2, 2]
    assert [item.reps for item in accessory.prescriptions] == ["10-15"] * 4
