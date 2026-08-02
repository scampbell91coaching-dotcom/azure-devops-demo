from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.exercise_library import DayTemplate, Exercise
from portal.models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)


def create_test_app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def test_seed_creates_exercises_and_templates():
    app = create_test_app()

    with app.app_context():
        assert Exercise.query.count() >= 3
        assert DayTemplate.query.count() >= 6


def test_exercise_library_loads():
    app = create_test_app()

    response = app.test_client().get("/exercise-library")

    assert response.status_code == 200
    assert b"Exercise library" in response.data


def test_create_exercise():
    app = create_test_app()

    response = app.test_client().post(
        "/exercise-library",
        data={
            "name": "Paused Squat",
            "movement": "squat",
            "category": "variation",
            "fatigue_rating": "4",
        },
    )

    assert response.status_code == 302

    with app.app_context():
        exercise = Exercise.query.filter_by(name="Paused Squat").one()

        assert exercise.movement == "squat"
        assert exercise.fatigue_rating == 4


def test_block_metrics():
    app = create_test_app()

    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@example.com",
        )
        block = TrainingBlock(
            athlete=athlete,
            name="Prep",
        )
        week = TrainingWeek(
            block=block,
            name="Week 1",
            position=1,
        )
        session = TrainingSession(
            week=week,
            name="SBD",
            position=1,
        )
        item = ExercisePrescription(
            session=session,
            exercise_name="Competition Squat",
            position=1,
            sets=4,
            reps="5",
            load_kg=180,
            rpe=7,
        )

        db.session.add_all([athlete, block, week, session, item])
        db.session.commit()

        block_id = block.id

    response = app.test_client().get(f"/programming/api/blocks/{block_id}/metrics")

    assert response.status_code == 200

    payload = response.get_json()

    assert payload["total_sets"] == 4
    assert payload["total_reps"] == 20
    assert payload["tonnage_kg"] == 3600
