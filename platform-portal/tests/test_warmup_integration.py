from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import ExercisePrescription, ProgrammingLiftSlot, TrainingBlock, TrainingSession, TrainingWeek
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
        assert WarmupPlanSnapshot.query.count() == 0


def test_lift_slot_form_target_and_first_successful_save_freeze_nonempty_delivery():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        athlete_id, _, session_id = _seed()
        session = db.session.get(TrainingSession, session_id)
        slot = ProgrammingLiftSlot(session=session, position=1, lift_family="squat")
        db.session.add(slot)
        db.session.commit()
        slot_id = slot.id
        prescription = session.prescriptions[0]
        prescription_id = prescription.id
    client = app.test_client()
    created = client.post(f"/programming/sessions/{session_id}/warmup-protocols", data={
        "name": "Pinned squat preparation", "reason": "Coach pin",
        "lift_slot_id": str(slot_id),
        "steps": "lift | Original squat drill | reps | 8",
    })
    assert created.status_code == 302
    with app.app_context():
        assignment = WarmupAssignment.query.one()
        assert assignment.lift_slot_id == slot_id
        assert WarmupPlanSnapshot.query.count() == 0

    with client.session_transaction() as signed_in:
        signed_in["athlete_id"] = athlete_id
    # Viewing is live and must not freeze delivery.
    assert client.get(f"/athlete/programme/sessions/{session_id}").status_code == 200
    with app.app_context():
        assert WarmupPlanSnapshot.query.count() == 0
    saved = client.post(f"/athlete/programme/sessions/{session_id}", data={
        f"row-{prescription_id}-1": "1",
        f"set-{prescription_id}-1-completed": "1",
        f"set-{prescription_id}-1-reps": "5",
        "intent": "save",
    })
    assert saved.status_code == 302
    with app.app_context():
        snapshot = WarmupPlanSnapshot.query.one()
        assert [step.name for step in snapshot.steps] == ["Original squat drill"]
        WarmupProtocol.query.one().steps[0].name = "Later coach edit"
        db.session.commit()

    delivered = client.get(f"/athlete/programme/sessions/{session_id}")
    assert b"Original squat drill" in delivered.data
    assert b"Later coach edit" not in delivered.data


def test_lift_slot_target_rejects_slot_from_another_session():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        _, _, session_id = _seed()
        session = db.session.get(TrainingSession, session_id)
        other = TrainingSession(week=session.week, name="Other", position=2)
        slot = ProgrammingLiftSlot(session=other, position=1, lift_family="bench")
        db.session.add(slot)
        db.session.commit()
        slot_id = slot.id
    response = app.test_client().post(
        f"/programming/sessions/{session_id}/warmup-protocols",
        data={"name": "Bad target", "reason": "No", "lift_slot_id": slot_id,
              "steps": "lift | Drill | reps | 5"},
    )
    assert response.status_code == 400


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
    with app.app_context():
        prescription_id = db.session.get(TrainingSession, session_id).prescriptions[0].id
    saved = client.post(f"/athlete/programme/sessions/{session_id}", data={
        f"row-{prescription_id}-1": "1",
        f"set-{prescription_id}-1-completed": "1",
        f"set-{prescription_id}-1-reps": "5",
        "intent": "save",
    })
    assert saved.status_code == 302
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
