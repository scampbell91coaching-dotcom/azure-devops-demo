import re

import pytest

from portal import create_app
from portal.block_factory import FactoryRequest, _day_sequence
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


def factory_request(training_days: int, squat: int, bench: int, deadlift: int):
    return FactoryRequest(
        athlete_id=1,
        name="Frequency test",
        week_count=1,
        training_days=training_days,
        split="POWERLIFTING_4",
        goal="development",
        squat_frequency=squat,
        bench_frequency=bench,
        deadlift_frequency=deadlift,
        deadlift_style="conventional",
        meet_date=None,
    )


@pytest.mark.parametrize(
    ("training_days", "squat", "bench", "deadlift", "expected"),
    [
        (3, 2, 3, 1, ["SB", "SBD", "B"]),
        (4, 2, 3, 1, ["SB", "BD", "SB", "ACCESSORY"]),
        (5, 2, 3, 1, ["SB", "BD", "S", "B", "ACCESSORY"]),
    ],
)
def test_frequency_scheduler_is_deterministic_and_exact(
    training_days, squat, bench, deadlift, expected
):
    schedule = _day_sequence(factory_request(training_days, squat, bench, deadlift))

    assert schedule == expected
    assert sum(day != "ACCESSORY" and "S" in day for day in schedule) == squat
    assert sum(day != "ACCESSORY" and "B" in day for day in schedule) == bench
    assert sum(day != "ACCESSORY" and "D" in day for day in schedule) == deadlift


@pytest.mark.parametrize(
    "training_days, squat, bench, deadlift, message",
    [
        (2, 1, 1, 1, "training days must be 3, 4, or 5"),
        (4, 5, 3, 1, "Squat frequency (5) exceeds the 4 training days"),
        (4, 0, 0, 0, "select at least one squat, bench, or deadlift exposure"),
    ],
)
def test_frequency_scheduler_rejects_impossible_requests(
    training_days, squat, bench, deadlift, message
):
    with pytest.raises(ValueError, match=re.escape(message)):
        _day_sequence(factory_request(training_days, squat, bench, deadlift))


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


def test_preview_and_generation_use_the_same_frequency_schedule():
    app = create_test_app()
    athlete_id = create_athlete(app)
    data = {
        "athlete_id": athlete_id,
        "name": "Frequency Block",
        "goal": "development",
        "split": "POWERLIFTING_4",
        "week_count": 1,
        "training_days": 4,
        "squat_frequency": 2,
        "bench_frequency": 3,
        "deadlift_frequency": 1,
        "deadlift_style": "conventional",
    }

    preview_response = app.test_client().post(
        "/programming/factory/preview",
        data=data,
    )
    generate_response = app.test_client().post("/programming/factory", data=data)

    assert preview_response.status_code == 200
    assert generate_response.status_code == 302
    expected_schedule = _day_sequence(factory_request(4, 2, 3, 1))
    for day_number, day_type in enumerate(expected_schedule, start=1):
        assert f"Day {day_number} \u00b7 {day_type}".encode() in preview_response.data

    with app.app_context():
        block = TrainingBlock.query.one()
        sessions = block.weeks[0].sessions
        assert [
            session.name.rsplit(" ", maxsplit=1)[1] for session in sessions
        ] == expected_schedule


def test_preview_rejects_an_impossible_frequency_combination():
    app = create_test_app()
    athlete_id = create_athlete(app)

    response = app.test_client().post(
        "/programming/factory/preview",
        data={
            "athlete_id": athlete_id,
            "training_days": 4,
            "squat_frequency": 5,
            "bench_frequency": 3,
            "deadlift_frequency": 1,
        },
    )

    assert response.status_code == 400
    assert b"Squat frequency (5) exceeds the 4 training days" in response.data


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
        first_week = block.weeks[0]
        exercise_names = [
            prescription.exercise_name
            for session in first_week.sessions
            for prescription in session.prescriptions
        ]
        assert sum(name == "Competition Squat" for name in exercise_names) == 2
        assert sum(name == "Competition Bench Press" for name in exercise_names) == 3
        assert sum(name == "Sumo Deadlift" for name in exercise_names) == 1
