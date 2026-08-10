import re
from dataclasses import replace

import pytest
from portal import create_app
from portal.block_factory import FactoryRequest, _day_sequence, _preview
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import AthleteStateOverride, AthleteStateRecommendation
from portal.models.exercise_library import Exercise
from portal.models.programming import TrainingBlock
from portal.services.athlete_state import SignalDraft
from portal.services.weekly_programming_intelligence import (
    WeeklyProgrammingIntelligence,
)


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


def preview_fields(response):
    proposal_id = re.search(rb'name="proposal_id" value="(\d+)"', response.data)
    integrity = re.search(
        rb'name="proposal_integrity" value="([0-9a-f]+)"', response.data
    )
    assert proposal_id and integrity
    return {
        "proposal_id": proposal_id.group(1).decode(),
        "proposal_integrity": integrity.group(1).decode(),
    }


def preview_and_accept(client, data):
    preview_response = client.post("/programming/factory/preview", data=data)
    assert preview_response.status_code == 200
    return preview_response, client.post(
        "/programming/factory", data=preview_fields(preview_response)
    )


@pytest.mark.parametrize(
    ("training_days", "squat", "bench", "deadlift"),
    [
        (3, 2, 3, 1),
        (4, 2, 3, 1),
        (5, 2, 3, 1),
    ],
)
def test_frequency_scheduler_is_deterministic_and_exact(
    training_days, squat, bench, deadlift
):
    schedule = _day_sequence(factory_request(training_days, squat, bench, deadlift))

    assert schedule == _day_sequence(
        factory_request(training_days, squat, bench, deadlift)
    )
    assert all(day and set(day) <= {"S", "B", "D"} for day in schedule)
    assert sum("S" in day for day in schedule) == squat
    assert sum("B" in day for day in schedule) == bench
    assert sum("D" in day for day in schedule) == deadlift


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
    generate_response = app.test_client().post(
        "/programming/factory", data=preview_fields(preview_response)
    )

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

    _preview_response, response = preview_and_accept(
        app.test_client(),
        {
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
        assert first_week.lift_slot_frequencies() == {
            "squat": 2,
            "bench": 3,
            "deadlift": 1,
        }
        assert sum(len(session.lift_slots) for session in first_week.sessions) == 6
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
        upper = Exercise(
            name="Chest Supported Row",
            movement="accessory",
            category="upper body",
            accessory_suitable=True,
        )
        lower = Exercise(
            name="Reverse Lunge",
            movement="accessory",
            category="lower body",
            accessory_suitable=True,
        )
        db.session.add_all([upper, lower])
        db.session.commit()
        accessory_ids = [str(upper.id), str(lower.id)]
    _preview_response, response = preview_and_accept(
        app.test_client(),
        {
            "athlete_id": athlete_id,
            "name": "Accessory catalogue",
            "week_count": 1,
            "training_days": 3,
            "squat_frequency": 1,
            "bench_frequency": 1,
            "deadlift_frequency": 1,
            "accessory_exercise_id": accessory_ids,
        },
    )
    assert response.status_code == 302
    with app.app_context():
        block = TrainingBlock.query.one()
        names = [
            item.exercise_name
            for session in block.weeks[0].sessions
            for item in session.prescriptions
        ]
        assert [
            name for name in names if name in {"Chest Supported Row", "Reverse Lunge"}
        ] == ["Chest Supported Row", "Reverse Lunge"]
        assistance = [
            item
            for session in block.weeks[0].sessions
            for item in session.prescriptions
            if item.exercise_name in {"Chest Supported Row", "Reverse Lunge"}
        ]
        assert [item.provenance for item in assistance] == [
            "coach_selected",
            "coach_selected",
        ]
        assert all(item.lift_slot_id is None for item in assistance)


def test_zero_assistance_is_preserved_without_a_quota():
    app = create_test_app()
    with app.app_context():
        request = factory_request(3, 1, 1, 1)
        days = _preview(request)
        assert all(day["accessory_count"] == 0 for day in days)


def test_factory_suggests_enabled_metadata_and_manual_selection_overrides_it():
    app = create_test_app()
    with app.app_context():
        suggested = Exercise(
            name="Development Row", movement="accessory", category="balancing",
            accessory_suitable=True, auto_select=True,
            lift_relevance='["bench"]', training_phases='["development"]',
            coach_priority=10, default_sets=4, default_reps="8-12",
        )
        pinned = Exercise(
            name="Coach Pin", movement="accessory", category="upper body",
            accessory_suitable=True,
        )
        db.session.add_all([suggested, pinned])
        db.session.commit()
        automatic = _preview(factory_request(3, 1, 1, 1))
        automatic_accessories = [item for day in automatic for item in day["accessories"]]
        assert [item["name"] for item in automatic_accessories] == ["Development Row"]
        assert automatic_accessories[0]["source"] == "Library suggestion"
        assert any("relevant to bench" in reason for reason in automatic_accessories[0]["reasons"])

        request = factory_request(3, 1, 1, 1)
        request = request.__class__(
            **{**request.__dict__, "accessory_exercise_ids": (pinned.id,)}
        )
        manual = _preview(request)
        assert [item["name"] for day in manual for item in day["accessories"]] == [
            "Coach Pin"
        ]


def test_accessory_volume_controls_deterministic_per_day_maximums():
    app = create_test_app()
    with app.app_context():
        for index in range(12):
            db.session.add(Exercise(
                name=f"Auto Accessory {index:02d}", movement="accessory",
                category="assistance", accessory_suitable=True, auto_select=True,
                lift_relevance='["all"]', coach_priority=12 - index,
            ))
        db.session.commit()
        request = factory_request(3, 1, 1, 1)

        low = _preview(replace(request, accessory_volume="low"))
        medium = _preview(replace(request, accessory_volume="medium"))
        high = _preview(replace(request, accessory_volume="high"))

        assert [day["accessory_count"] for day in low] == [1, 1, 1]
        assert [day["accessory_count"] for day in medium] == [2, 2, 2]
        assert [day["accessory_count"] for day in high] == [3, 3, 3]
        assert [item["name"] for day in medium for item in day["accessories"]] == [
            item["name"] for day in _preview(replace(request, accessory_volume="medium"))
            for item in day["accessories"]
        ]


def test_deadlift_grip_context_prioritises_explainable_grip_work():
    app = create_test_app()
    with app.app_context():
        db.session.add_all([
            Exercise(
                name="General Posterior Chain", movement="accessory",
                category="assistance", accessory_suitable=True, auto_select=True,
                lift_relevance='["deadlift"]', coach_priority=10,
            ),
            Exercise(
                name="Hook-Grip Practice Hold", movement="accessory",
                category="grip", accessory_suitable=True, auto_select=True,
                lift_relevance='["deadlift"]', coach_priority=1,
            ),
        ])
        db.session.commit()
        preview = _preview(replace(
            factory_request(3, 1, 1, 1), accessory_volume="low",
            deadlift_grip="hook", grip_work_priority="priority",
            training_strap_usage="most",
        ))
        deadlift_day = next(day for day in preview if "D" in day["day_type"])

        assert deadlift_day["accessories"][0]["name"] == "Hook-Grip Practice Hold"
        assert "competition grip is hook" in deadlift_day["accessories"][0]["reasons"]


def test_zero_assistance_generation_persists_after_reload():
    app = create_test_app()
    athlete_id = create_athlete(app)
    data = {
        "athlete_id": athlete_id,
        "name": "No assistance",
        "week_count": 1,
        "training_days": 3,
        "squat_frequency": 1,
        "bench_frequency": 1,
        "deadlift_frequency": 1,
    }
    _preview_response, accepted = preview_and_accept(app.test_client(), data)
    assert accepted.status_code == 302
    with app.app_context():
        block_id = TrainingBlock.query.one().id
        db.session.expire_all()
        reloaded = db.session.get(TrainingBlock, block_id)
        for session in reloaded.weeks[0].sessions:
            day_type = session.name.rsplit("·", 1)[1].strip()
            assert len(session.prescriptions) == len(day_type)
            assert [item.position for item in session.prescriptions] == list(
                range(1, len(session.prescriptions) + 1)
            )
            assert len(session.lift_slots) == len(day_type)


def base_form(athlete_id):
    return {
        "athlete_id": athlete_id,
        "name": "Safe proposal",
        "week_count": 1,
        "training_days": 3,
        "squat_frequency": 1,
        "bench_frequency": 1,
        "deadlift_frequency": 1,
        "goal": "development",
        "deadlift_style": "conventional",
    }


def test_non_assistance_main_lift_post_is_rejected_even_when_active():
    app = create_test_app()
    athlete_id = create_athlete(app)
    with app.app_context():
        lift = Exercise(
            name="Crafted Main Lift",
            movement="squat",
            category="main",
            lift_family="squat",
            accessory_suitable=False,
            active=True,
        )
        db.session.add(lift)
        db.session.commit()
        lift_id = lift.id
    response = app.test_client().post(
        "/programming/factory/preview",
        data={**base_form(athlete_id), "accessory_exercise_id": str(lift_id)},
    )
    assert response.status_code == 400
    assert b"selected accessories are unavailable" in response.data


def test_incomplete_state_and_rpe_adherence_do_not_infer_fatigue(monkeypatch):
    app = create_test_app()
    athlete_id = create_athlete(app)
    monkeypatch.setattr(
        "portal.services.weekly_programming_intelligence.calculate_signals",
        lambda athlete: [SignalDraft("rpe_adherence_rate", 0.5, (), "bounded")],
    )
    response = app.test_client().post(
        "/programming/factory/preview", data=base_form(athlete_id)
    )
    assert response.status_code == 200
    assert b"50% of comparable sets" in response.data
    assert b"Reported fatigue:" not in response.data
    assert b"Incomplete data:" in response.data


def test_active_coach_override_is_surfaced_as_authoritative():
    app = create_test_app()
    athlete_id = create_athlete(app)
    with app.app_context():
        db.session.add(
            AthleteStateOverride(
                athlete_id=athlete_id,
                target_type="programming",
                target_ref="weekly",
                override_json={"bench_frequency": 2},
                reason="Coach-selected recovery week",
                recorded_by="coach@example.com",
            )
        )
        db.session.commit()
    response = app.test_client().post(
        "/programming/factory/preview", data=base_form(athlete_id)
    )
    assert response.status_code == 200
    assert b"Active coach overrides are authoritative" in response.data
    assert b"Coach-selected recovery week" in response.data
    assert b"2 bench" in response.data


def test_exposure_metadata_uses_exact_taxonomy_not_name_substrings():
    app = create_test_app()
    athlete_id = create_athlete(app)
    with app.app_context():
        exercise = Exercise.query.filter_by(name="Competition Squat").one()
        exercise.lift_family = "bench"
        exercise.movement_pattern = "horizontal_press"
        db.session.commit()
        athlete = db.session.get(Athlete, athlete_id)
        factory = factory_request(3, 1, 1, 1)
        preview = _preview(factory)
        result = WeeklyProgrammingIntelligence().preview(factory, athlete, preview)
        squat_metadata = next(
            metadata
            for day in result.weekly_structure
            for name, metadata in zip(day["exposures"], day["exposure_taxonomy"])
            if name == "Competition Squat"
        )
        assert squat_metadata["lift_family"] == "bench"
        assert squat_metadata["movement_pattern"] == "horizontal_press"


def test_proposal_integrity_staleness_replay_and_provenance():
    app = create_test_app()
    athlete_id = create_athlete(app)
    client = app.test_client()
    preview_response = client.post(
        "/programming/factory/preview", data=base_form(athlete_id)
    )
    fields = preview_fields(preview_response)

    tampered = client.post(
        "/programming/factory",
        data={**fields, "proposal_integrity": "0" * 64},
    )
    assert tampered.status_code == 409

    accepted = client.post("/programming/factory", data=fields)
    assert accepted.status_code == 302
    replayed = client.post("/programming/factory", data=fields)
    assert replayed.status_code == 409
    with app.app_context():
        proposal = db.session.get(
            AthleteStateRecommendation, int(fields["proposal_id"])
        )
        assert proposal.status == "accepted"
        assert proposal.decided_by == "test-coach"
        assert proposal.decided_at is not None
        assert TrainingBlock.query.count() == 1


def test_stale_proposal_is_rejected_when_athlete_state_changes():
    app = create_test_app()
    athlete_id = create_athlete(app)
    client = app.test_client()
    response = client.post("/programming/factory/preview", data=base_form(athlete_id))
    fields = preview_fields(response)
    with app.app_context():
        db.session.add(
            AthleteStateOverride(
                athlete_id=athlete_id,
                target_type="programming",
                target_ref="weekly",
                override_json={"training_days": 3},
                reason="New coach decision",
                recorded_by="coach@example.com",
            )
        )
        db.session.commit()
    stale = client.post("/programming/factory", data=fields)
    assert stale.status_code == 409
    with app.app_context():
        assert TrainingBlock.query.count() == 0


def test_edit_requires_reason_and_records_override_provenance():
    app = create_test_app()
    athlete_id = create_athlete(app)
    client = app.test_client()
    original = client.post("/programming/factory/preview", data=base_form(athlete_id))
    fields = preview_fields(original)
    edited_data = {**base_form(athlete_id), **fields, "name": "Coach edit"}
    missing_reason = client.post("/programming/factory/preview", data=edited_data)
    assert missing_reason.status_code == 400
    edited = client.post(
        "/programming/factory/preview",
        data={**edited_data, "override_reason": "Match the coach-authored block label"},
    )
    assert edited.status_code == 200
    with app.app_context():
        original_proposal = db.session.get(
            AthleteStateRecommendation, int(fields["proposal_id"])
        )
        override = AthleteStateOverride.query.one()
        assert original_proposal.status == "superseded"
        assert original_proposal.decided_by == "test-coach"
        assert override.reason == "Match the coach-authored block label"
        assert override.recorded_by == "test-coach"
