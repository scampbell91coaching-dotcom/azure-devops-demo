from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import TrainingBlock


def create_test_app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def create_athlete(app) -> int:
    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@example.com",
        )
        db.session.add(athlete)
        db.session.commit()
        return athlete.id


def test_factory_v3_page_loads():
    app = create_test_app()
    create_athlete(app)

    response = app.test_client().get("/programming/factory")

    assert response.status_code == 200
    assert b"Block Factory" in response.data
    assert b"Meet date" in response.data


def test_factory_preview_loads():
    app = create_test_app()
    athlete_id = create_athlete(app)

    response = app.test_client().post(
        "/programming/factory/preview",
        data={
            "athlete_id": athlete_id,
            "name": "Preview Block",
            "goal": "development",
            "split": "POWERLIFTING_4",
            "week_count": 4,
            "training_days": 4,
            "squat_frequency": 2,
            "bench_frequency": 3,
            "deadlift_frequency": 1,
            "deadlift_style": "conventional",
        },
    )

    assert response.status_code == 200
    assert b"Preview Block" in response.data
    assert b"Day 1" in response.data


def test_factory_v3_generates_complete_block():
    app = create_test_app()
    athlete_id = create_athlete(app)

    response = app.test_client().post(
        "/programming/factory",
        data={
            "athlete_id": athlete_id,
            "name": "Generated Prep",
            "goal": "strength",
            "split": "POWERLIFTING_4",
            "week_count": 3,
            "training_days": 4,
            "squat_frequency": 2,
            "bench_frequency": 3,
            "deadlift_frequency": 1,
            "deadlift_style": "sumo",
        },
    )

    assert response.status_code == 302

    with app.app_context():
        block = TrainingBlock.query.one()

        assert len(block.weeks) == 3
        assert sum(len(week.sessions) for week in block.weeks) == 12
        assert all(
            session.prescriptions for week in block.weeks for session in week.sessions
        )
