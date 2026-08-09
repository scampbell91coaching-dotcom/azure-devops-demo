from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import ExercisePrescription, TrainingBlock, TrainingSession, TrainingWeek
from portal.models.warmup import WarmupAssignment, WarmupPlanSnapshot, WarmupProtocol


def _seed():
    athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@example.com")
    other = Athlete(first_name="Sam", last_name="Lifter", email="sam@example.com")
    block = TrainingBlock(athlete=athlete, name="Beta", status="active")
    week = TrainingWeek(block=block, name="Week 1", position=1)
    session = TrainingSession(week=week, name="Squat", position=1)
    session.prescriptions.append(ExercisePrescription(exercise_name="Squat", position=1, sets=1, reps="5"))
    db.session.add_all([athlete, other, block])
    db.session.commit()
    return athlete.id, other.id, session.id


def test_coach_creates_reusable_plan_and_athlete_sees_snapshot_before_work_sets():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        athlete_id, _, session_id = _seed()
    client = app.test_client()
    response = client.post(f"/programming/sessions/{session_id}/warmup-protocols", data={
        "name": "Squat preparation", "reason": "Session preparation",
        "steps": "general | Bike | duration | 180 | 1 | 30 | Easy pace\nbarbell | Empty bar | barbell | 5@20kg | 2 | 60",
    })
    assert response.status_code == 302
    with client.session_transaction() as signed_in:
        signed_in["athlete_id"] = athlete_id
    page = client.get(f"/athlete/programme/sessions/{session_id}")
    assert page.status_code == 200
    assert page.data.index(b"Warm-up") < page.data.index(b"Work sets")
    assert b"Bike" in page.data and b"3" in page.data and b"Empty bar" in page.data
    with app.app_context():
        assert WarmupProtocol.query.one().version == 1
        assert WarmupAssignment.query.one().reason == "Session preparation"
        assert [step.source_version for step in WarmupPlanSnapshot.query.one().steps] == [1, 1]


def test_manual_override_is_ordered_and_snapshot_locks_history():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        athlete_id, _, session_id = _seed()
    client = app.test_client()
    client.post(f"/programming/sessions/{session_id}/warmup-protocols", data={"name": "Base", "reason": "Required", "steps": "general | Bike | duration | 120"})
    client.post(f"/programming/sessions/{session_id}/warmup-overrides", data={"action": "append", "phase": "20", "name": "Coach choice", "kind": "reps", "value": "8", "sets": "1", "reason": "Athlete-specific"})
    with client.session_transaction() as signed_in: signed_in["athlete_id"] = athlete_id
    page = client.get(f"/athlete/programme/sessions/{session_id}")
    assert page.data.index(b"Bike") < page.data.index(b"Coach choice")
    locked = client.post(f"/programming/sessions/{session_id}/warmup-overrides", data={"action": "append", "phase": "20", "name": "Late edit", "kind": "reps", "value": "5", "reason": "Too late"})
    assert locked.status_code == 409
    assert b"Late edit" not in client.get(f"/athlete/programme/sessions/{session_id}").data


def test_athlete_cannot_view_another_athletes_warmup():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        _, other_id, session_id = _seed()
    client = app.test_client()
    with client.session_transaction() as signed_in: signed_in["athlete_id"] = other_id
    assert client.get(f"/athlete/programme/sessions/{session_id}").status_code == 404
