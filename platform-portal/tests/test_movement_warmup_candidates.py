import json
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
from portal.models.programming import (
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from portal.models.warmup import WarmupAssignment, WarmupProtocol, WarmupProtocolStep
from portal.services.movement_warmup_candidates import (
    MAPPING_VERSION,
    movement_needs,
    warmup_candidates,
)


@pytest.fixture()
def app():
    instance = create_app(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}
    )
    with instance.app_context():
        db.create_all()
    return instance


def seed(lift="squat"):
    athlete = Athlete(first_name="Alex", last_name="Lifter", email="moves@test")
    block = TrainingBlock(athlete=athlete, name="Block", status="draft")
    week = TrainingWeek(block=block, name="Week", position=1)
    session = TrainingSession(week=week, name="Session", position=1)
    session.lift_slots.append(ProgrammingLiftSlot(position=1, lift_family=lift))
    db.session.add(athlete)
    db.session.flush()
    return athlete, session


def observe(athlete, text, day, lift="squat"):
    db.session.add(
        CoachTechnicalObservation(
            athlete=athlete,
            lift=lift,
            observation=text,
            observed_on=day,
            recorded_by="coach@test",
        )
    )


def protocol(key, version=1, name=None):
    item = WarmupProtocol(
        stable_key=key, version=version, name=name or key.replace("-", " ").title()
    )
    item.steps.append(
        WarmupProtocolStep(
            position=1, phase=30, name="Coach-authored drill", kind="reps", sets=1, reps=5
        )
    )
    db.session.add(item)
    return item


def test_match_has_full_provenance_and_uses_latest_protocol_version(app):
    with app.app_context():
        athlete, session = seed()
        observe(athlete, "Hip shift on rep four", date(2026, 8, 1))
        observe(athlete, "Hip shift again", date(2026, 8, 8))
        protocol("squat-hip-shift-preparation", 1)
        expected = protocol("squat-hip-shift-preparation", 2)
        db.session.commit()

        candidate = warmup_candidates(
            athlete.id, session, as_of=date(2026, 8, 9)
        )[0]

        assert candidate.protocol_id == expected.id
        assert candidate.protocol_version == 2
        assert candidate.rule_id == "technical.repeated_hip_shift.v1"
        assert candidate.rule_version == "coaching-rules-v1"
        assert candidate.mapping_version == MAPPING_VERSION
        assert candidate.source_ids == (
            "coach_technical_observation:1",
            "coach_technical_observation:2",
        )
        assert "does not" not in candidate.reason.casefold()


def test_non_match_contrary_evidence_wrong_lift_and_missing_protocol(app):
    with app.app_context():
        athlete, bench_session = seed("bench")
        observe(athlete, "Hip shift", date(2026, 8, 1))
        observe(athlete, "Hip shift", date(2026, 8, 2))
        protocol("squat-hip-shift-preparation")
        db.session.commit()
        assert warmup_candidates(
            athlete.id, bench_session, as_of=date(2026, 8, 9)
        ) == ()

        bench_session.lift_slots[0].lift_family = "squat"
        observe(athlete, "Hip shift resolved", date(2026, 8, 8))
        db.session.commit()
        assert warmup_candidates(
            athlete.id, bench_session, as_of=date(2026, 8, 9)
        ) == ()

        assert movement_needs(athlete.id, as_of=date(2026, 6, 1)) == ()


def test_lift_constraint_mapping_and_order_are_deterministic(app):
    with app.app_context():
        athlete, session = seed()
        observe(athlete, "Heel lifts", date(2026, 8, 1))
        observe(athlete, "Heel pressure lost", date(2026, 8, 2))
        observe(athlete, "Hip shift", date(2026, 8, 3))
        observe(athlete, "Hip shift", date(2026, 8, 4))
        db.session.add(
            AthleteConstraintFlag(
                athlete=athlete,
                flag_kind="constraint",
                label="Squat constraint",
                reported_by="coach",
                starts_on=date(2026, 8, 1),
            )
        )
        protocol("squat-heel-pressure-preparation")
        protocol("squat-hip-shift-preparation")
        protocol("squat-constraint-preparation")
        db.session.commit()

        first = warmup_candidates(athlete.id, session, as_of=date(2026, 8, 9))
        second = warmup_candidates(athlete.id, session, as_of=date(2026, 8, 9))

        assert first == second
        assert [item.rule_id for item in first] == [
            "constraint.active_lift_family.v1:squat",
            "technical.repeated_heel_pressure.v1",
            "technical.repeated_hip_shift.v1",
        ]


def test_coach_override_is_explained_and_manual_assignment_remains_valid(app):
    with app.app_context():
        athlete, session = seed()
        observe(athlete, "Hip shift", date.today())
        observe(athlete, "Hip shift again", date.today())
        candidate_protocol = protocol("squat-hip-shift-preparation")
        manual_protocol = protocol("coach-manual-plan")
        db.session.flush()
        db.session.add_all(
            [
                AthleteStateOverride(
                    athlete=athlete,
                    target_type="coaching_rule",
                    target_ref="technical.repeated_hip_shift.v1",
                    override_json={"recommendation": "Use my reviewed warm-up choice."},
                    reason="Coach reviewed video",
                    recorded_by="coach@test",
                ),
                WarmupAssignment(
                    protocol_id=manual_protocol.id,
                    athlete_id=athlete.id,
                    session_id=session.id,
                    reason="Existing manual warm-up",
                ),
            ]
        )
        db.session.commit()

        item = warmup_candidates(athlete.id, session)[0]
        assert item.protocol_id == candidate_protocol.id
        assert item.reason == "Use my reviewed warm-up choice."
        assert item.coach_override["reason"] == "Coach reviewed video"
        assert WarmupAssignment.query.filter_by(reason="Existing manual warm-up").one()


def test_candidate_requires_explicit_coach_acceptance_and_persists_provenance(app):
    with app.app_context():
        athlete, session = seed()
        observe(athlete, "Hip shift", date.today())
        observe(athlete, "Hip shift again", date.today())
        selected = protocol("squat-hip-shift-preparation", 3, "Hip shift preparation")
        db.session.commit()
        athlete_id, session_id, protocol_id = athlete.id, session.id, selected.id
        assert WarmupAssignment.query.count() == 0

    client = app.test_client()
    page = client.get(f"/programming/sessions/{session_id}")
    assert b"Suggestions only" in page.data
    with app.app_context():
        assert WarmupAssignment.query.count() == 0
    response = client.post(
        f"/programming/sessions/{session_id}/warmup-candidates/accept",
        data={"protocol_id": protocol_id},
    )
    assert response.status_code == 302

    with app.app_context():
        assignment = WarmupAssignment.query.one()
        provenance = json.loads(assignment.reason)
        assert assignment.athlete_id == athlete_id
        assert provenance["candidate"] == "movement_warmup"
        assert provenance["protocol_version"] == 3
        assert provenance["rule"] == "technical.repeated_hip_shift.v1"
        assert provenance["sources"] == [
            "coach_technical_observation:1",
            "coach_technical_observation:2",
        ]

    repeat = client.post(
        f"/programming/sessions/{session_id}/warmup-candidates/accept",
        data={"protocol_id": protocol_id},
    )
    assert repeat.status_code == 409


def test_left_sided_low_back_hip_observation_proposes_authored_drills_deterministically(app):
    with app.app_context():
        athlete, session = seed("deadlift")
        session.week.block.objective = "Build strength through controlled volume"
        observe(
            athlete,
            "Coach observed left-sided low-back and hip presentation",
            date(2026, 8, 8),
            lift="deadlift",
        )
        protocol("reverse-lunge", name="Reverse lunge")
        protocol("wall-flamingo", name="Wall flamingo")
        db.session.commit()

        first = warmup_candidates(athlete.id, session, as_of=date(2026, 8, 9))
        second = warmup_candidates(athlete.id, session, as_of=date(2026, 8, 9))

        assert first == second
        assert [item.protocol_key for item in first] == [
            "reverse-lunge",
            "wall-flamingo",
        ]
        assert {item.rule_id for item in first} == {
            "warmup.observation.left_low_back_hip.v1"
        }
        assert all(item.action == "consider" for item in first)
        assert all(item.block_intent == "strength" for item in first)
        assert all(
            item.source_ids == ("coach_technical_observation:1",) for item in first
        )


def test_sided_rule_requires_full_evidence_and_suitable_session_context(app):
    with app.app_context():
        athlete, session = seed("bench")
        observe(
            athlete,
            "Left-sided low-back and hip presentation",
            date(2026, 8, 8),
            lift="squat",
        )
        protocol("wall-flamingo")
        db.session.commit()
        assert warmup_candidates(athlete.id, session, as_of=date(2026, 8, 9)) == ()

        session.lift_slots[0].lift_family = "squat"
        session.week.block.objective = "Competition peaking"
        db.session.commit()
        assert warmup_candidates(athlete.id, session, as_of=date(2026, 8, 9)) == ()


def test_elbow_irritation_changes_bench_prep_and_coach_can_remove_suggestion(app):
    with app.app_context():
        athlete, session = seed("bench")
        flag = AthleteConstraintFlag(
            athlete=athlete,
            flag_kind="irritation",
            label="Elbow",
            details="Irritable during pressing",
            reported_by="coach",
            starts_on=date(2026, 8, 8),
        )
        selected = protocol("bench-elbow-irritation-preparation")
        db.session.add(flag)
        db.session.commit()
        candidate = warmup_candidates(athlete.id, session, as_of=date(2026, 8, 9))[0]
        assert candidate.rule_id == "warmup.constraint.elbow_irritation.v1"
        athlete_id, session_id, protocol_id = athlete.id, session.id, selected.id

    response = app.test_client().post(
        f"/programming/sessions/{session_id}/warmup-candidates/override",
        data={
            "protocol_id": protocol_id,
            "action": "remove",
            "reason": "Coach selected a different upper-body preparation",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        assert warmup_candidates(athlete_id, db.session.get(TrainingSession, session_id)) == ()
        override = AthleteStateOverride.query.filter_by(
            target_type="warmup_selection_rule"
        ).one()
        assert override.override_json == {"action": "remove"}
