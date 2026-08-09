from datetime import date

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import (
    AthleteConstraintFlag,
    AthleteStateOverride,
    CoachTechnicalObservation,
)
from portal.services.coaching_rules import (
    decide_candidate,
    evaluate_coaching_rules,
    persist_candidates,
)


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with instance.app_context():
        db.create_all()
    return instance


def athlete() -> Athlete:
    item = Athlete(first_name="Alex", last_name="Lifter", email="rules@example.test")
    db.session.add(item)
    db.session.flush()
    return item


def observation(item, text, on, *, lift="squat"):
    db.session.add(CoachTechnicalObservation(
        athlete=item, lift=lift, observation=text, observed_on=on,
        recorded_by="coach@example.test",
    ))


def test_repeated_observation_threshold_matches_with_complete_provenance(app):
    with app.app_context():
        item = athlete()
        observation(item, "Hip shift visible above parallel", date(2026, 8, 1))
        observation(item, "Hip shift repeated on final rep", date(2026, 8, 8))
        db.session.commit()

        candidates = evaluate_coaching_rules(item.id, as_of=date(2026, 8, 9))

        assert len(candidates) == 1
        candidate = candidates[0]
        assert candidate["rule_id"] == "technical.repeated_hip_shift.v1"
        assert candidate["priority"] == 70
        assert candidate["confidence"] == "moderate"
        assert "at least 2" in candidate["matched_conditions"][1]
        assert len(candidate["source_observations"]) == 2
        assert all(
            source["reference"].startswith("coach_technical_observation:")
            for source in candidate["source_observations"]
        )
        assert "does not identify an injury" in candidate["not_claiming"]
        assert candidate["mutates_programming"] is False
        assert "coach must accept" in candidate["coach_authority"]


def test_rule_does_not_match_below_threshold_outside_window_or_wrong_lift(app):
    with app.app_context():
        item = athlete()
        observation(item, "Hip shift", date(2026, 8, 8))
        observation(item, "Hip shift", date(2026, 7, 1))
        observation(item, "Hip shift", date(2026, 8, 8), lift="deadlift")
        db.session.commit()

        assert evaluate_coaching_rules(item.id, as_of=date(2026, 8, 9)) == []


def test_conflicting_observation_prevents_ambiguous_match(app):
    with app.app_context():
        item = athlete()
        observation(item, "Hip shift on first rep", date(2026, 8, 1))
        observation(item, "Hip shift again", date(2026, 8, 3))
        observation(item, "Hip shift resolved in today's session", date(2026, 8, 8))
        db.session.commit()

        assert evaluate_coaching_rules(item.id, as_of=date(2026, 8, 9)) == []


def test_active_lift_constraint_matches_but_resolved_and_generic_flags_do_not(app):
    with app.app_context():
        item = athlete()
        db.session.add_all([
            AthleteConstraintFlag(
                athlete=item, flag_kind="constraint", label="Active squat constraint",
                reported_by="coach", starts_on=date(2026, 8, 1),
            ),
            AthleteConstraintFlag(
                athlete=item, flag_kind="constraint", label="Schedule constraint",
                reported_by="athlete", starts_on=date(2026, 8, 1),
            ),
            AthleteConstraintFlag(
                athlete=item, flag_kind="irritation", label="Bench irritation",
                reported_by="athlete", starts_on=date(2026, 7, 1),
                resolved_on=date(2026, 8, 2),
            ),
        ])
        db.session.commit()

        candidates = evaluate_coaching_rules(item.id, as_of=date(2026, 8, 9))

        assert [candidate["rule_id"] for candidate in candidates] == [
            "constraint.active_lift_family.v1:squat"
        ]
        assert candidates[0]["source_observations"][0]["type"] == "constraint_flag"
        assert "not a medical diagnosis" in candidates[0]["not_claiming"]


def test_order_is_priority_then_rule_id_and_is_stable_across_insertion_order(app):
    with app.app_context():
        item = athlete()
        observation(item, "Heels lift", date(2026, 8, 8))
        observation(item, "Hip shift", date(2026, 8, 7))
        db.session.add(AthleteConstraintFlag(
            athlete=item, flag_kind="constraint", label="Deadlift constraint",
            reported_by="coach", starts_on=date(2026, 8, 1),
        ))
        observation(item, "Hip shift", date(2026, 8, 8))
        observation(item, "Heel lifts", date(2026, 8, 7))
        db.session.commit()

        first = evaluate_coaching_rules(item.id, as_of=date(2026, 8, 9))
        second = evaluate_coaching_rules(item.id, as_of=date(2026, 8, 9))

        expected = [
            "constraint.active_lift_family.v1:deadlift",
            "technical.repeated_hip_shift.v1",
            "technical.repeated_heel_pressure.v1",
        ]
        assert [row["rule_id"] for row in first] == expected
        assert first == second


def test_persisted_candidate_can_be_rejected_without_programming_side_effect(app):
    with app.app_context():
        item = athlete()
        observation(item, "Hip shift", date(2026, 8, 7))
        observation(item, "Hip shift", date(2026, 8, 8))
        db.session.commit()

        record = persist_candidates(item.id, as_of=date(2026, 8, 9))[0]
        db.session.flush()
        decide_candidate(
            record, decision="rejected", decided_by="coach@example.test",
            reason="Video review changed my assessment",
        )
        db.session.commit()

        assert record.status == "dismissed"
        assert (
            record.recommendation_json["coach_decision"]["reason"]
            == "Video review changed my assessment"
        )
        assert record.decided_by == "coach@example.test"


def test_persisted_candidate_can_be_accepted_by_coach(app):
    with app.app_context():
        item = athlete()
        observation(item, "Hip shift", date(2026, 8, 7))
        observation(item, "Hip shift", date(2026, 8, 8))
        db.session.commit()

        record = persist_candidates(item.id, as_of=date(2026, 8, 9))[0]
        decide_candidate(
            record, decision="accepted", decided_by="coach@example.test"
        )
        db.session.commit()

        assert record.status == "accepted"
        assert record.decided_by == "coach@example.test"


def test_override_requires_reason_and_replaces_future_candidate_guidance(app):
    with app.app_context():
        item = athlete()
        observation(item, "Hip shift", date(2026, 8, 7))
        observation(item, "Hip shift", date(2026, 8, 8))
        db.session.commit()
        record = persist_candidates(item.id, as_of=date(2026, 8, 9))[0]

        with pytest.raises(ValueError, match="require a reason"):
            decide_candidate(
                record, decision="overridden", decided_by="coach@example.test",
                replacement="Use coach-selected review notes.",
            )
        decide_candidate(
            record, decision="overridden", decided_by="coach@example.test",
            reason="I reviewed both camera angles",
            replacement="Use coach-selected review notes.",
        )
        db.session.commit()

        candidate = evaluate_coaching_rules(item.id, as_of=date(2026, 8, 9))[0]
        assert record.status == "dismissed"
        assert candidate["recommendation"] == "Use coach-selected review notes."
        assert candidate["coach_override"] == {
            "id": 1,
            "reason": "I reviewed both camera angles",
            "recorded_by": "coach@example.test",
            "replacement_applied": True,
        }
        assert AthleteStateOverride.query.count() == 1
