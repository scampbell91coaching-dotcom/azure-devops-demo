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
