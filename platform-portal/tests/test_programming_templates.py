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
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
    return app


def test_factory_2_3_1_creates_sbd_sb_b():
    app = create_test_app()
    with app.app_context():
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.com"
        )
        db.session.add(athlete)
        db.session.commit()
        athlete_id = athlete.id
    response = app.test_client().post(
        "/programming/block-factory",
        data={
            "athlete_id": athlete_id,
            "name": "Offseason",
            "weeks": 2,
            "squat_days": 2,
            "bench_days": 3,
            "deadlift_days": 1,
        },
    )
    assert response.status_code == 302
    with app.app_context():
        assert TrainingBlock.query.count() == 1
        assert TrainingWeek.query.count() == 2
        assert TrainingSession.query.count() == 6
        assert ExercisePrescription.query.count() == 12
