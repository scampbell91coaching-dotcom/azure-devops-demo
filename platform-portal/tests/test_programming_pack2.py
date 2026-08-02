from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)


def create_test_app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )

    with app.app_context():
        db.create_all()

    return app


def seed(app):
    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@example.com",
        )
        block = TrainingBlock(athlete=athlete, name="Prep")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        session = TrainingSession(week=week, name="Lower", position=1)
        item = ExercisePrescription(
            session=session,
            exercise_name="Competition Squat",
            position=1,
            sets=4,
            reps="5",
            rpe=7,
        )

        db.session.add_all([athlete, block, week, session, item])
        db.session.commit()

        return session.id, item.id


def test_autosave_update():
    app = create_test_app()
    _, item_id = seed(app)

    response = app.test_client().patch(
        f"/programming/api/prescriptions/{item_id}",
        json={
            "exercise_name": "Paused Squat",
            "sets": "5",
            "rpe": "7.5",
        },
    )

    assert response.status_code == 200

    with app.app_context():
        item = db.session.get(ExercisePrescription, item_id)
        assert item.exercise_name == "Paused Squat"
        assert item.sets == 5
        assert item.rpe == 7.5


def test_delete_row():
    app = create_test_app()
    _, item_id = seed(app)

    response = app.test_client().delete(f"/programming/api/prescriptions/{item_id}")

    assert response.status_code == 204

    with app.app_context():
        assert ExercisePrescription.query.count() == 0


def test_add_row_api():
    app = create_test_app()
    session_id, _ = seed(app)

    response = app.test_client().post(
        f"/programming/api/sessions/{session_id}/prescriptions",
        json={
            "exercise_name": "Paused Bench",
            "sets": "4",
            "reps": "6",
        },
    )

    assert response.status_code == 201

    with app.app_context():
        assert ExercisePrescription.query.count() == 2
