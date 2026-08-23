from __future__ import annotations

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import AthleteStateOverride
from portal.models.programming import (
    ExercisePrescription, ProgrammeRevision, ProgrammingLiftSlot, TrainingBlock,
    TrainingSession, TrainingWeek,
)
from portal.services.adaptation_policy import (
    AdaptationEvidence, ConservativeAdaptationPolicy, apply_adjustment_to_graph,
    create_adaptation_proposal, decide_adaptation, programme_graph,
)
from portal.programming_services.revisions import append_revision


def ev(signal, value, period, family="squat"):
    return AdaptationEvidence(signal, value, period, (f"source:{period}",), family)


def test_one_poor_week_does_not_rewrite_and_repeated_rpe_overshoot_lowers_rpe():
    policy = ConservativeAdaptationPolicy()
    assert policy.evaluate([ev("rpe_drift", 1.5, "w1")]).decision == "maintain"
    result = policy.evaluate([ev("rpe_drift", 1.2, "w1"), ev("rpe_drift", 1.0, "w2")])
    assert (result.decision, result.adjustment.kind, result.adjustment.amount) == ("recommend", "lower_rpe", .5)
    assert result.adjustment.preserves_frequency and result.adjustment.preserves_exercise


def test_soreness_reduces_sets_and_pain_can_intervene_early_with_stability():
    policy = ConservativeAdaptationPolicy()
    soreness = policy.evaluate([ev("soreness", 8, "w1"), ev("soreness", 7, "w2")])
    assert (soreness.adjustment.kind, soreness.adjustment.amount) == ("reduce_sets", 1)
    pain = policy.evaluate([ev("pain_increase", 3, "w1")])
    assert pain.adjustment.kind == "increase_stability"
    assert pain.adjustment.preserves_frequency and not pain.adjustment.preserves_exercise


def test_graph_adjustments_preserve_structure_and_exercise_where_possible():
    graph = {"weeks": [{"sessions": [{"prescriptions": [{
        "exercise_name": "Competition Squat", "sets": 4, "rpe": 8,
        "lift_slot": {"lift_family": "squat"},
    }]}]}]}
    policy = ConservativeAdaptationPolicy()
    sets = policy.evaluate([ev("soreness", 8, "w1"), ev("soreness", 8, "w2")]).adjustment
    changed = apply_adjustment_to_graph(graph, sets)
    assert changed["weeks"][0]["sessions"][0]["prescriptions"][0] == {
        "exercise_name": "Competition Squat", "sets": 3, "rpe": 8,
        "lift_slot": {"lift_family": "squat"},
    }
    assert graph["weeks"][0]["sessions"][0]["prescriptions"][0]["sets"] == 4


def _app():
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "SECRET_KEY": "wave6"})


def _block():
    athlete = Athlete(first_name="Wave", last_name="Six", email="wave6@example.test")
    block = TrainingBlock(athlete=athlete, name="Accepted", status="active")
    week = TrainingWeek(block=block, name="Week 1", position=1)
    session = TrainingSession(week=week, name="Day 1", position=1)
    slot = ProgrammingLiftSlot(session=session, position=1, lift_family="squat", exposure_role="competition")
    ExercisePrescription(session=session, lift_slot=slot, slot_role="top_set", provenance="coach_authored",
                         exercise_name="Competition Squat", position=1, prescription_type="rpe",
                         sets=4, reps="4", rpe=8)
    db.session.add(block); db.session.flush()
    append_revision(block, change_type="accepted", summary="Accepted programme")
    db.session.commit()
    return block


def test_coach_reject_override_and_accept_use_proposal_revision_path_without_regeneration():
    app = _app()
    with app.app_context():
        original = _block()
        original_graph = programme_graph(original)
        recommendation = ConservativeAdaptationPolicy().evaluate([
            ev("soreness", 8, "w1"), ev("soreness", 8, "w2")
        ])

        rejected = create_adaptation_proposal(original, recommendation)
        db.session.flush(); decide_adaptation(rejected, action="reject", decided_by="coach")
        assert rejected.status == "dismissed" and TrainingBlock.query.count() == 1

        overridden = create_adaptation_proposal(original, recommendation); db.session.flush()
        replacement_graph = apply_adjustment_to_graph(original_graph, recommendation.adjustment)
        replacement_graph["block"]["name"] = "Coach override"
        replacement = decide_adaptation(overridden, action="override", decided_by="coach",
                                         override_programme=replacement_graph, override_reason="Coach chose exact revision")
        db.session.flush()
        assert overridden.status == "superseded" and replacement.status == "proposed"
        assert AthleteStateOverride.query.one().reason == "Coach chose exact revision"

        signed = replacement.recommendation_json["programme"]
        revised = decide_adaptation(replacement, action="accept", decided_by="coach")
        db.session.commit()
        assert original.status == "active" and programme_graph(original) == original_graph
        assert revised.status == "draft" and revised.name == signed["block"]["name"]
        assert revised.weeks[0].sessions[0].prescriptions[0].sets == 3
        assert revised.weeks[0].sessions[0].lift_slots[0].exposure_role == "competition"
        assert ProgrammeRevision.query.filter_by(block_id=original.id).one().authored_snapshot["block"]["name"] == "Accepted"
        revision = ProgrammeRevision.query.filter_by(block_id=revised.id).one()
        assert revision.change_type == "athlete_state_adaptation"
