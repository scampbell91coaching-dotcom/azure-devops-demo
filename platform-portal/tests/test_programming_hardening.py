from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.exercise_library import Exercise
from portal.models.programming import (
    ExercisePrescription, ProgrammeRevision, TrainingBlock, TrainingSession, TrainingWeek,
)
from portal.programming_services.blocks import activate, duplicate


def _app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
    return app


def _valid_block(athlete, name="Programme"):
    block = TrainingBlock(athlete=athlete, name=name)
    week = TrainingWeek(block=block, name="Week 1", position=1)
    session = TrainingSession(week=week, name="Day 1", position=1)
    session.prescriptions.append(ExercisePrescription(
        exercise_name="Rows", position=1, prescription_type="rpe",
        sets=3, reps="8", rpe=7, provenance="coach_authored",
    ))
    db.session.add(block)
    db.session.commit()
    return block


def test_publication_rejects_incomplete_graph_atomically():
    app = _app()
    with app.app_context():
        athlete = Athlete(first_name="Ada", last_name="Lifter", email="ada@test")
        active = _valid_block(athlete, "Visible")
        active.status = "active"
        incomplete = TrainingBlock(athlete=athlete, name="Incomplete")
        db.session.add(incomplete)
        db.session.commit()
        incomplete_id, active_id = incomplete.id, active.id
    response = app.test_client().post(f"/programming/blocks/{incomplete_id}/activate")
    assert response.status_code == 409
    assert b"Add at least one week" in response.data
    with app.app_context():
        assert db.session.get(TrainingBlock, active_id).status == "active"
        assert db.session.get(TrainingBlock, incomplete_id).status == "draft"


def test_valid_publish_and_material_review_are_atomic_and_reasoned():
    app = _app()
    with app.app_context():
        athlete = Athlete(first_name="Ada", last_name="Lifter", email="ada@test")
        original = _valid_block(athlete, "Visible")
        activate(original)
        draft = duplicate(original, as_revision=True)
        draft.objective = "Reviewed objective"
        db.session.commit()
        original_id, draft_id = original.id, draft.id
    missing = app.test_client().post(f"/programming/blocks/{draft_id}/activate")
    assert missing.status_code == 409
    assert b"reason is required" in missing.data
    with app.app_context():
        assert db.session.get(TrainingBlock, original_id).status == "active"
        assert db.session.get(TrainingBlock, draft_id).status == "draft"
    published = app.test_client().post(
        f"/programming/blocks/{draft_id}/activate",
        data={"revision_reason": "Adjusted after athlete review"},
    )
    assert published.status_code == 302
    with app.app_context():
        assert db.session.get(TrainingBlock, original_id).status == "archived"
        assert db.session.get(TrainingBlock, draft_id).status == "active"
        revision = ProgrammeRevision.query.filter_by(
            block_id=draft_id, change_type="material_change_published"
        ).one()
        assert revision.reason == "Adjusted after athlete review"
        assert "replacing" in revision.summary


def test_stale_block_week_reorder_and_publish_are_recoverable():
    app = _app()
    with app.app_context():
        athlete = Athlete(first_name="Ada", last_name="Lifter", email="ada@test")
        block = _valid_block(athlete)
        second = TrainingWeek(block=block, name="Week 2", position=2)
        db.session.add(second)
        db.session.commit()
        block_id, week_id = block.id, second.id
    client = app.test_client()
    stale_edit = client.post(
        f"/programming/blocks/{block_id}/edit",
        data={"name": "Overwrite", "expected_revision": "999"},
    )
    stale_week = client.post(
        f"/programming/weeks/{week_id}/edit",
        data={"name": "Overwrite", "expected_revision": "999"},
    )
    stale_reorder = client.post(
        f"/programming/weeks/{week_id}/reorder",
        data={"position": "1", "expected_revision": "999"},
    )
    stale_publish = client.post(
        f"/programming/blocks/{block_id}/activate",
        data={"expected_revision": "999"},
    )
    assert [r.status_code for r in (stale_edit, stale_week, stale_reorder, stale_publish)] == [409] * 4
    assert all(b"changed since you opened it" in r.data for r in (stale_edit, stale_week, stale_reorder, stale_publish))
    with app.app_context():
        saved = db.session.get(TrainingBlock, block_id)
        assert saved.name == "Programme" and saved.status == "draft"
        assert db.session.get(TrainingWeek, week_id).position == 2
