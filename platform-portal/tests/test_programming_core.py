from datetime import UTC, datetime, timedelta

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import (
    ExercisePrescription,
    ProgrammeRevision,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)


def app_with_db():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
    return app


def test_programming_page_loads():
    app = app_with_db()
    response = app.test_client().get("/programming")
    assert response.status_code == 200
    assert b"<h1>Programming</h1>" in response.data
    assert b"<h1>Training blocks</h1>" not in response.data


def test_create_full_programming_hierarchy():
    app = app_with_db()
    client = app.test_client()
    with app.app_context():
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.com"
        )
        db.session.add(athlete)
        db.session.commit()
        athlete_id = athlete.id

    assert (
        client.post(
            "/programming/blocks", data={"athlete_id": athlete_id, "name": "Prep"}
        ).status_code
        == 302
    )
    with app.app_context():
        block_id = TrainingBlock.query.one().id
    assert (
        client.post(
            f"/programming/blocks/{block_id}/weeks", data={"name": "Week 1"}
        ).status_code
        == 302
    )
    with app.app_context():
        week_id = TrainingWeek.query.one().id
    assert (
        client.post(
            f"/programming/weeks/{week_id}/sessions", data={"name": "Lower 1"}
        ).status_code
        == 302
    )
    with app.app_context():
        session_id = TrainingSession.query.one().id
    assert (
        client.post(
            f"/programming/sessions/{session_id}/prescriptions",
            data={
                "exercise_name": "Competition Squat",
                "sets": "4",
                "reps": "5",
                "rpe": "7",
            },
        ).status_code
        == 302
    )
    with app.app_context():
        item = ExercisePrescription.query.one()
        assert item.exercise_name == "Competition Squat"
        assert item.sets == 4
        assert item.rpe == 7


def test_duplicate_week_copies_programming():
    app = app_with_db()
    with app.app_context():
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.com"
        )
        block = TrainingBlock(athlete=athlete, name="Prep")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        session = TrainingSession(week=week, name="Lower 1", position=1)
        item = ExercisePrescription(
            session=session, exercise_name="Squat", position=1, sets=4, reps="4"
        )
        db.session.add_all([athlete, block, week, session, item])
        db.session.commit()
        week_id = week.id
    assert (
        app.test_client().post(f"/programming/weeks/{week_id}/duplicate").status_code
        == 302
    )
    with app.app_context():
        assert TrainingWeek.query.count() == 2
        assert TrainingSession.query.count() == 2
        assert ExercisePrescription.query.count() == 2


def _athlete_with_programme(app):
    with app.app_context():
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.com"
        )
        block = TrainingBlock(athlete=athlete, name="Development", status="draft")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        session = TrainingSession(week=week, name="Lower 1", position=1)
        prescription = ExercisePrescription(
            session=session,
            exercise_name="Squat",
            position=1,
            sets=4,
            reps="4",
        )
        db.session.add_all([athlete, block, week, session, prescription])
        db.session.commit()
        return athlete.id, block.id


def test_athlete_programme_empty_state_offers_generation():
    app = app_with_db()
    with app.app_context():
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.com"
        )
        db.session.add(athlete)
        db.session.commit()
        athlete_id = athlete.id

    response = app.test_client().get(f"/athletes/{athlete_id}/programming")

    assert response.status_code == 200
    assert b"No programme blocks yet" in response.data
    assert f"/programming/factory?athlete_id={athlete_id}".encode() in response.data

    factory = app.test_client().get(f"/programming/factory?athlete_id={athlete_id}")
    assert factory.status_code == 200
    assert f'value="{athlete_id}"'.encode() in factory.data
    assert b"selected" in factory.data


def test_athlete_programme_shows_active_current_then_drafts_and_history():
    app = app_with_db()
    with app.app_context():
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.com"
        )
        start = datetime(2026, 1, 1, tzinfo=UTC)
        older = TrainingBlock(
            athlete=athlete,
            name="Older",
            status="archived",
            created_at=start,
        )
        newer = TrainingBlock(
            athlete=athlete,
            name="Newer",
            status="archived",
            created_at=start + timedelta(days=1),
        )
        current = TrainingBlock(
            athlete=athlete,
            name="Current",
            status="active",
            created_at=start + timedelta(days=2),
        )
        db.session.add_all([athlete, older, newer, current])
        db.session.commit()
        athlete_id = athlete.id

    response = app.test_client().get(f"/athletes/{athlete_id}/programming")
    page = response.data.decode()

    assert response.status_code == 200
    assert "Current block" in page
    assert page.index("Current") < page.index("Newer") < page.index("Older")


def test_draft_publish_lifecycle_and_duplicate_active_conflict_persist():
    app = app_with_db()
    client = app.test_client()
    with app.app_context():
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.com"
        )
        other = Athlete(
            first_name="Sam", last_name="Lifter", email="sam@example.com"
        )
        draft = TrainingBlock(athlete=athlete, name="Next block")
        other_draft = TrainingBlock(athlete=other, name="Private draft")
        db.session.add_all([draft, other_draft])
        db.session.commit()
        athlete_id = athlete.id
        draft_id = draft.id

    with client.session_transaction() as session:
        session["athlete_id"] = athlete_id
    draft_page = client.get("/athlete/programme").data
    assert b"Next block" not in draft_page
    assert b"Private draft" not in draft_page

    published = client.post(f"/programming/blocks/{draft_id}/activate")
    assert published.status_code == 302
    assert b"Next block" in client.get("/athlete/programme").data

    with app.app_context():
        db.session.remove()
        assert db.session.get(TrainingBlock, draft_id).status == "active"
        conflict = TrainingBlock(
            athlete_id=athlete_id, name="Conflicting draft", status="draft"
        )
        db.session.add(conflict)
        db.session.commit()
        conflict_id = conflict.id

    response = client.post(f"/programming/blocks/{conflict_id}/activate")
    assert response.status_code == 409
    assert b"Archive the active programme" in response.data
    with app.app_context():
        assert db.session.get(TrainingBlock, conflict_id).status == "draft"


def test_activation_rejects_missing_athlete_association():
    app = app_with_db()
    with app.app_context():
        block = TrainingBlock(athlete_id=999999, name="Orphaned draft")
        db.session.add(block)
        db.session.commit()
        block_id = block.id

    response = app.test_client().post(f"/programming/blocks/{block_id}/activate")

    assert response.status_code == 404


def test_duplicate_block_copies_full_programme_as_a_draft():
    app = app_with_db()
    _, block_id = _athlete_with_programme(app)

    response = app.test_client().post(f"/programming/blocks/{block_id}/duplicate")

    assert response.status_code == 302
    with app.app_context():
        copied = TrainingBlock.query.filter_by(name="Development Copy").one()
        assert copied.status == "draft"
        assert len(copied.weeks) == 1
        assert len(copied.weeks[0].sessions) == 1
        assert copied.weeks[0].sessions[0].prescriptions[0].exercise_name == "Squat"


def test_edit_block_metadata_keeps_programming_structure():
    app = app_with_db()
    _, block_id = _athlete_with_programme(app)
    response = app.test_client().post(
        f"/programming/blocks/{block_id}/edit",
        data={"name": "Revised development", "objective": "Build capacity"},
    )
    assert response.status_code == 302
    with app.app_context():
        block = db.session.get(TrainingBlock, block_id)
        assert (block.name, block.objective) == ("Revised development", "Build capacity")
        assert len(block.weeks) == 1 and len(block.weeks[0].sessions) == 1


def test_archive_block_removes_it_from_current_programme():
    app = app_with_db()
    athlete_id, block_id = _athlete_with_programme(app)

    response = app.test_client().post(f"/programming/blocks/{block_id}/archive")

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(TrainingBlock, block_id).status == "archived"
    page = app.test_client().get(f"/athletes/{athlete_id}/programming").data
    assert b"Current block" not in page
    assert b"Development" in page


def test_delete_draft_block_removes_its_programming_and_rejects_non_drafts():
    app = app_with_db()
    _, block_id = _athlete_with_programme(app)

    response = app.test_client().post(f"/programming/blocks/{block_id}/delete")

    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(TrainingBlock, block_id) is None
        assert TrainingWeek.query.count() == 0
        assert TrainingSession.query.count() == 0
        assert ExercisePrescription.query.count() == 0

        athlete = Athlete(first_name="Sam", last_name="Lifter", email="sam@example.com")
        active_block = TrainingBlock(
            athlete=athlete,
            name="Active",
            status="active",
        )
        db.session.add_all([athlete, active_block])
        db.session.commit()
        active_block_id = active_block.id

    assert (
        app.test_client()
        .post(f"/programming/blocks/{active_block_id}/delete")
        .status_code
        == 409
    )


def test_delete_draft_block_preserves_completed_history_snapshots():
    app = app_with_db()
    athlete_id, block_id = _athlete_with_programme(app)
    with app.app_context():
        block = db.session.get(TrainingBlock, block_id)
        session = block.weeks[0].sessions[0]
        prescription = session.prescriptions[0]
        log = TrainingSessionLog(
            athlete_id=athlete_id,
            session=session,
            session_name=session.name,
            block_name=block.name,
            week_name=block.weeks[0].name,
            status="completed",
            completed_at=datetime.now(UTC),
        )
        result = TrainingSetResult(
            session_log=log,
            prescription=prescription,
            exercise_name=prescription.exercise_name,
            exercise_position=1,
            set_order=1,
            actual_load_kg=100,
            actual_reps=5,
            actual_rpe=7,
            completed=True,
        )
        db.session.add_all([log, result])
        db.session.commit()
        log_id, result_id = log.id, result.id
        revision = ProgrammeRevision(
            block=block,
            athlete_id=athlete_id,
            revision_number=1,
            change_type="created",
            summary="Created draft",
            reason="Created draft",
            authored_snapshot={"block": block.name},
            authored_by="Coach",
        )
        db.session.add(revision)
        db.session.commit()
        revision_id = revision.id

    assert app.test_client().post(f"/programming/blocks/{block_id}/delete").status_code == 302
    with app.app_context():
        log = db.session.get(TrainingSessionLog, log_id)
        result = db.session.get(TrainingSetResult, result_id)
        assert log is not None and log.session_id is None and log.block_name == "Development"
        assert result is not None and result.prescription_id is None
        revision = db.session.get(ProgrammeRevision, revision_id)
        assert revision is not None and revision.block_id is None
