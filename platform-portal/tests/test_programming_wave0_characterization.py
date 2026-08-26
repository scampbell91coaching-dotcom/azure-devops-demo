from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from portal import create_app
from portal.block_factory import FactoryRequest, _preview
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import AthleteStateRecommendation
from portal.models.programming import (
    ExercisePrescription, ProgrammeRevision, ProgrammingLiftSlot, TrainingBlock,
    TrainingSession, TrainingSessionLog, TrainingSetResult, TrainingWeek,
)

from programming_graph import (
    normalize_persisted,
    normalize_persisted_programme,
    normalize_preview,
)


@pytest.fixture()
def app():
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "SECRET_KEY": "wave0-characterization"})


def _athlete(app, email="wave0@example.test"):
    with app.app_context():
        row = Athlete(first_name="Wave", last_name="Zero", email=email)
        db.session.add(row)
        db.session.commit()
        return row.id


def _form(athlete_id, **changes):
    values = {"athlete_id": athlete_id, "name": "Wave 0 golden", "week_count": 2,
              "training_days": 3, "squat_frequency": 2, "bench_frequency": 2,
              "deadlift_frequency": 1, "goal": "development", "deadlift_style": "conventional",
              "accessory_mode": "none"}
    values.update(changes)
    return values


def _preview_fields(response):
    proposal = re.search(rb'name="proposal_id" value="(\d+)"', response.data)
    integrity = re.search(rb'name="proposal_integrity" value="([0-9a-f]+)"', response.data)
    assert proposal and integrity
    return {"proposal_id": proposal.group(1).decode(), "proposal_integrity": integrity.group(1).decode()}


def test_current_preview_graph_is_deterministic_and_ordered(app):
    with app.app_context():
        request = FactoryRequest(athlete_id=1, name="Golden", week_count=2, training_days=3,
            split="POWERLIFTING_4", goal="development", squat_frequency=2,
            bench_frequency=2, deadlift_frequency=1, deadlift_style="conventional",
            meet_date=None, accessory_mode="none")
        first = _preview(request)
        assert first == _preview(request)
        assert [(d["day"], d["day_type"]) for d in first] == [(1, "B"), (2, "SB"), (3, "SD")]
        assert [[e["lift_family"] for e in d["exposures"]] for d in first] == [["bench"], ["squat", "bench"], ["squat", "deadlift"]]
        assert [[e["purpose"] for e in d["exposures"]] for d in first] == [["competition_intensity"], ["positional", "competition_volume"], ["competition", "competition"]]
        assert [[e["exercise_name"] for e in d["exposures"]] for d in first] == [["Competition Bench Press"], ["Pause Squat", "Competition Bench Press"], ["Competition Squat", "Conventional Deadlift"]]
        assert all(d["accessories"] == [] and d["exercises"] == [e["exercise_name"] for e in d["exposures"]] for d in first)


def test_acceptance_persists_exact_signed_graph_order_provenance_status_and_revision(app):
    athlete_id = _athlete(app)
    client = app.test_client()
    preview_response = client.post("/programming/factory/preview", data=_form(athlete_id))
    fields = _preview_fields(preview_response)
    with app.app_context():
        proposal = db.session.get(AthleteStateRecommendation, int(fields["proposal_id"]))
        preview_graph = normalize_preview(proposal.recommendation_json)
        signed_programme = proposal.recommendation_json["programme"]
    assert client.post("/programming/factory", data=fields).status_code == 302
    with app.app_context():
        proposal = db.session.get(AthleteStateRecommendation, int(fields["proposal_id"]))
        block = TrainingBlock.query.one()
        persisted = normalize_persisted(block)
        assert preview_graph["block"]["week_count"] == len(persisted["weeks"]) == 2
        assert [len(w["sessions"]) for w in persisted["weeks"]] == [3, 3]
        assert [[s["position"] for s in w["sessions"]] for w in persisted["weeks"]] == [[1, 2, 3], [1, 2, 3]]
        assert [[p["position"] for p in s["prescriptions"]] for s in persisted["weeks"][0]["sessions"]] == [[1], [1, 2], [1, 2]]
        assert all(p["provenance"] == "generated" for s in persisted["weeks"][0]["sessions"] for p in s["prescriptions"])
        assert proposal.status == "accepted" and proposal.decided_at is not None
        revisions = ProgrammeRevision.query.order_by(ProgrammeRevision.revision_number).all()
        assert [(r.revision_number, r.change_type) for r in revisions] == [(1, "factory_programme_created")]
        assert revisions[0].authored_snapshot["weeks"][0]["sessions"][0]["prescriptions"][0]["exercise_name"] == "Competition Bench Press"
        # Wave 1 closes the characterized divergence: the signed, persistable
        # proposal graph is now the authoritative acceptance boundary.
        assert normalize_persisted_programme(block) == signed_programme


@pytest.mark.parametrize("tamper", ["generator_version", "athlete_id"])
def test_signed_proposal_version_and_identity_cannot_be_changed(app, tamper):
    athlete_id = _athlete(app)
    client = app.test_client()
    response = client.post("/programming/factory/preview", data=_form(athlete_id))
    fields = _preview_fields(response)
    with app.app_context():
        proposal = db.session.get(AthleteStateRecommendation, int(fields["proposal_id"]))
        payload = dict(proposal.recommendation_json)
        if tamper == "generator_version":
            payload["generator_version"] = "forged-version"
        else:
            payload["factory"] = {**payload["factory"], "athlete_id": athlete_id + 999}
        proposal.recommendation_json = payload
        db.session.commit()
    rejected = client.post("/programming/factory", data=fields)
    assert rejected.status_code == 409
    with app.app_context():
        assert TrainingBlock.query.count() == 0
        assert db.session.get(AthleteStateRecommendation, int(fields["proposal_id"])).status == "proposed"


@pytest.mark.parametrize("role", ["competition", "primary_volume", "secondary_strength", "overload"])
def test_legacy_exposure_roles_load_render_serialize_and_survive_unrelated_history_write(app, role):
    athlete_id = _athlete(app, f"{role}@example.test")
    with app.app_context():
        block = TrainingBlock(athlete_id=athlete_id, name=f"Historical {role}")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        session = TrainingSession(week=week, name="Legacy day", day_label="Monday", position=1)
        slot = ProgrammingLiftSlot(session=session, position=1, lift_family="squat", exposure_role=role)
        ExercisePrescription(session=session, lift_slot=slot, slot_role="top_set", provenance="coach_authored", exercise_name="Historical Squat", position=1, sets=3, reps="5", rpe=7, notes="Do not regenerate")
        db.session.add(block); db.session.commit(); block_id = block.id
        before = normalize_persisted(block)
        block.objective = "Unrelated metadata edit"; db.session.commit(); db.session.expire_all()
        after = normalize_persisted(db.session.get(TrainingBlock, block_id))
        assert before["weeks"] == after["weeks"]
        assert after["weeks"][0]["sessions"][0]["prescriptions"][0]["exposure_role"] == role
    response = app.test_client().get(f"/programming/blocks/{block_id}")
    assert response.status_code == 200


def test_completed_training_history_and_accepted_block_survive_unrelated_programme_operation(app):
    athlete_id = _athlete(app)
    with app.app_context():
        old = TrainingBlock(athlete_id=athlete_id, name="Accepted history", status="active")
        week = TrainingWeek(block=old, name="Week 1", position=1)
        session = TrainingSession(week=week, name="Completed day", position=1)
        prescription = ExercisePrescription(session=session, exercise_name="Coach Squat", position=1, provenance="coach_authored", sets=1, reps="1", rpe=8)
        log = TrainingSessionLog(athlete_id=athlete_id, session=session, session_name="Completed day", block_name="Accepted history", week_name="Week 1", status="completed", completed_at=datetime.now(UTC))
        result = TrainingSetResult(session_log=log, prescription=prescription, exercise_name="Coach Squat", exercise_position=1, set_order=1, prescribed_reps="1", prescribed_rpe=8, completed=True, actual_load_kg=200, actual_reps=1, actual_rpe=9, athlete_note="Historical result")
        db.session.add_all([old, log]); db.session.commit(); old_id, log_id, result_id = old.id, log.id, result.id
    client = app.test_client(); preview = client.post("/programming/factory/preview", data=_form(athlete_id, name="Unrelated new proposal", week_count=1)); assert preview.status_code == 200
    with app.app_context():
        assert db.session.get(TrainingBlock, old_id).status == "active"
        stored_log = db.session.get(TrainingSessionLog, log_id); stored = db.session.get(TrainingSetResult, result_id)
        assert (stored_log.status, stored_log.completed_at is not None) == ("completed", True)
        assert (stored.actual_load_kg, stored.actual_reps, stored.actual_rpe, stored.athlete_note) == (200, 1, 9, "Historical result")
