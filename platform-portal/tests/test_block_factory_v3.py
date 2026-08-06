import re

import pytest

from portal import create_app
from portal.block_factory import FactoryRequest, _accessory_target, _day_sequence, _preview
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.exercise_library import Exercise
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


def test_factory_uses_multiple_ordered_catalogue_accessories():
    app = create_test_app()
    athlete_id = create_athlete(app)
    with app.app_context():
        upper = Exercise(name="Chest Supported Row", movement="accessory", category="upper body", accessory_suitable=True)
        lower = Exercise(name="Reverse Lunge", movement="accessory", category="lower body", accessory_suitable=True)
        db.session.add_all([upper, lower])
        db.session.commit()
        accessory_ids = [str(upper.id), str(lower.id)]
    response = app.test_client().post("/programming/factory", data={
        "athlete_id": athlete_id, "name": "Accessory catalogue", "week_count": 1,
        "training_days": 3, "squat_frequency": 1, "bench_frequency": 1,
        "deadlift_frequency": 1, "accessory_exercise_id": accessory_ids,
    })
    assert response.status_code == 302
    with app.app_context():
        block = TrainingBlock.query.one()
        for session in block.weeks[0].sessions:
            names = [item.exercise_name for item in session.prescriptions]
            assert names[-2:] == ["Chest Supported Row", "Reverse Lunge"]


@pytest.mark.parametrize(
    ("mode", "minimum", "maximum"),
    [("minimal", 1, 2), ("standard", 3, 4), ("high", 5, 6)],
)
def test_accessory_volume_modes_generate_within_range(mode, minimum, maximum):
    app = create_test_app()
    with app.app_context():
        request = factory_request(3, 1, 1, 1)
        request = FactoryRequest(**{**request.__dict__, "accessory_volume": mode})
        days = _preview(request)
        assert all(
            _accessory_target(request, day["day_type"])[0]
            <= day["accessory_count"]
            <= _accessory_target(request, day["day_type"])[1]
            for day in days
        )
        assert all(len(day["accessories"]) == len({item["name"] for item in day["accessories"]}) for day in days)


@pytest.mark.parametrize(
    ("day_type", "expected"),
    [("S", (3, 4)), ("B", (4, 5)), ("D", (3, 4)), ("SBD", (2, 4))],
)
def test_standard_lift_aware_accessory_defaults(day_type, expected):
    assert _accessory_target(factory_request(3, 1, 1, 1), day_type) == expected


def test_custom_exact_accessory_count_and_stable_balanced_output():
    app = create_test_app()
    with app.app_context():
        base = factory_request(3, 1, 1, 1)
        request = FactoryRequest(**{
            **base.__dict__, "accessory_volume": "custom",
            "accessory_count_min": 6, "accessory_count_max": 6,
            "accessory_emphasis": ("trunk",),
        })
        first = _preview(request)
        second = _preview(request)
        assert first == second
        assert all(day["accessory_count"] == 6 for day in first)
        assert all(len({item["role"] for item in day["accessories"]}) >= 4 for day in first)


def test_deadlift_day_guards_lower_back_fatigue():
    app = create_test_app()
    with app.app_context():
        request = factory_request(3, 0, 0, 1)
        request = FactoryRequest(**{**request.__dict__, "accessory_volume": "high"})
        deadlift_day = next(day for day in _preview(request) if day["day_type"] == "D")
        risky = ("good morning", "barbell row", "pendlay", "back extension", "romanian deadlift")
        assert not any(term in item["name"].casefold() for item in deadlift_day["accessories"] for term in risky)


def test_automatic_accessories_do_not_repeat_across_a_week():
    app = create_test_app()
    with app.app_context():
        days = _preview(factory_request(5, 2, 3, 1))
        generated = [
            item["name"]
            for day in days
            for item in day["accessories"]
            if item["source"] == "Generated"
        ]
        assert len(generated) == len(set(generated))


def test_custom_count_http_generation_persists_after_reload():
    app = create_test_app()
    athlete_id = create_athlete(app)
    data = {
        "athlete_id": athlete_id, "name": "Exact accessories", "week_count": 1,
        "training_days": 3, "squat_frequency": 1, "bench_frequency": 1,
        "deadlift_frequency": 1, "accessory_volume": "custom",
        "accessory_count_min": 4, "accessory_count_max": 4,
    }
    assert app.test_client().post("/programming/factory/preview", data=data).status_code == 200
    assert app.test_client().post("/programming/factory", data=data).status_code == 302
    with app.app_context():
        block_id = TrainingBlock.query.one().id
        db.session.expire_all()
        reloaded = db.session.get(TrainingBlock, block_id)
        for session in reloaded.weeks[0].sessions:
            day_type = session.name.rsplit("·", 1)[1].strip()
            main_count = 0 if day_type == "ACCESSORY" else len(day_type)
            assert len(session.prescriptions) - main_count == 4
            assert [item.position for item in session.prescriptions] == list(range(1, len(session.prescriptions) + 1))
