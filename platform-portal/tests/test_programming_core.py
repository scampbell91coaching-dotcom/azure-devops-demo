from datetime import UTC, datetime, timedelta

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
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
    assert b"Training blocks" in response.data


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


def test_athlete_programme_shows_current_then_previous_newest_first():
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
            status="draft",
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
