from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import AthleteStateFact, AthleteStateOverride
from portal.models.programming import ExercisePrescription, ProgrammeRevision, TrainingBlock, TrainingSession, TrainingWeek
from portal.programming_services.revisions import authored_snapshot, structured_diff


def _app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
    return app


def _programme(app):
    with app.app_context():
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="wave3@example.com")
        block = TrainingBlock(athlete=athlete, name="Meet prep")
        first = TrainingWeek(block=block, name="Base", position=1)
        second = TrainingWeek(block=block, name="Build", position=2)
        session = TrainingSession(week=first, name="Lower with a deliberately long exercise name", position=1)
        row = ExercisePrescription(session=session, exercise_name="Paused squat", position=1,
                                   prescription_type="rpe", sets=3, reps="5", rpe_min=7, rpe_max=8)
        db.session.add_all([athlete, block, first, second, session, row])
        db.session.commit()
        return block.id, first.id, second.id, row.id


def test_whole_block_review_shows_completeness_state_pins_and_canonical_links():
    app = _app()
    block_id, _, _, _ = _programme(app)
    with app.app_context():
        block = db.session.get(TrainingBlock, block_id)
        db.session.add(AthleteStateFact(athlete_id=block.athlete_id, fact_type="bodyweight",
            value_json={"kg": 90}, source_type="athlete", source_ref="checkin:8"))
        db.session.add(AthleteStateOverride(athlete_id=block.athlete_id, target_type="programming",
            target_ref="squat", override_json={"variation": "paused"}, reason="Technique priority",
            recorded_by="coach@example.com"))
        db.session.commit()
    response = app.test_client().get(f"/programming/blocks/{block_id}")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Whole-block programming review" in html
    assert "Week 2 has no sessions" in html
    assert "Paused squat" in html and "3 x 5 @ RPE 7-8" in html
    assert "checkin:8" in html
    assert "Technique priority" in html and "no expiry" in html
    assert "/programming/weeks/" in html and "/programming/sessions/" in html


def test_bulk_progression_previews_then_applies_exact_scope_with_revision():
    app = _app()
    block_id, first_id, second_id, row_id = _programme(app)
    client = app.test_client()
    preview = client.post(f"/programming/blocks/{block_id}/bulk-preview", data={
        "expected_revision": "0", "week_id": str(first_id), "field": "sets", "value": "4"})
    assert preview.status_code == 200
    assert "Preview 1 changes" in preview.get_data(as_text=True)
    applied = client.post(f"/programming/blocks/{block_id}/bulk-apply", data={
        "expected_revision": "0", "week_id": str(first_id), "field": "sets", "value": "4",
        "revision_reason": "Planned volume progression"})
    assert applied.status_code == 302
    with app.app_context():
        assert db.session.get(ExercisePrescription, row_id).sets == 4
        revision = ProgrammeRevision.query.one()
        assert revision.reason == "Planned volume progression"
        assert revision.change_type == "bulk_progression"
    stale = client.post(f"/programming/blocks/{block_id}/bulk-apply", data={
        "expected_revision": "0", "week_id": str(second_id), "field": "sets", "value": "5",
        "revision_reason": "stale"})
    assert stale.status_code == 409


def test_rpe_range_round_trips_through_primary_editor():
    app = _app()
    _, _, _, row_id = _programme(app)
    response = app.test_client().post(f"/programming/prescriptions/{row_id}", data={
        "exercise_name": "Paused squat", "prescription_type": "rpe", "sets": "4", "reps": "4",
        "rpe_min": "8", "rpe_max": "9"})
    assert response.status_code == 302
    with app.app_context():
        row = db.session.get(ExercisePrescription, row_id)
        assert (row.rpe, row.rpe_min, row.rpe_max) == (None, 8, 9)
        assert row.summary == "4 x 4 @ RPE 8-9"


def test_session_copy_forward_requires_preview_and_preserves_provenance():
    app = _app()
    block_id, _, second_id, row_id = _programme(app)
    with app.app_context():
        source = db.session.get(ExercisePrescription, row_id)
        source.provenance = "coach_selected"
        session_id = source.session_id
        db.session.commit()
    client = app.test_client()
    preview = client.post(f"/programming/sessions/{session_id}/copy-forward-preview", data={
        "expected_revision": "0", "target_week_id": str(second_id)})
    assert preview.status_code == 200
    assert "Paused squat" in preview.get_data(as_text=True)
    copied = client.post(f"/programming/sessions/{session_id}/copy-forward", data={
        "expected_revision": "0", "target_week_id": str(second_id)})
    assert copied.status_code == 302
    with app.app_context():
        target = db.session.get(TrainingWeek, second_id).sessions[0]
        assert target.prescriptions[0].provenance == "coach_selected"
        assert target.prescriptions[0].summary == "3 x 5 @ RPE 7-8"
        assert ProgrammeRevision.query.one().change_type == "session_copied_forward"


def test_structured_diff_reports_material_value_and_ignores_position():
    before = {"block": {"name": "Prep"}, "weeks": [{"id": 1, "position": 1, "name": "W1", "notes": None,
        "sessions": [{"id": 2, "position": 1, "name": "Day", "day_label": None, "notes": None,
        "prescriptions": [{"id": 3, "position": 1, "exercise_name": "Squat", "sets": 3}]}]}]}
    after = {"block": {"name": "Prep"}, "weeks": [{"id": 1, "position": 2, "name": "W1", "notes": None,
        "sessions": [{"id": 2, "position": 2, "name": "Day", "day_label": None, "notes": None,
        "prescriptions": [{"id": 3, "position": 2, "exercise_name": "Squat", "sets": 4}]}]}]}
    changes = structured_diff(before, after)
    assert [(row["field"], row["old"], row["new"]) for row in changes] == [("sets", 3, 4)]
