import re
from datetime import date
from dataclasses import replace

import pytest
from portal import create_app
from portal.block_factory import (
    FactoryRequest,
    _allocate_weekly_sets,
    _day_sequence,
    _preview,
)
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import AthleteConstraintFlag, AthleteStateOverride, AthleteStateRecommendation
from portal.models.exercise_library import Exercise
from portal.models.programming import TrainingBlock
from portal.models.warmup import WarmupAssignment
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


def test_frequency_scheduler_exhaustively_covers_every_valid_1_to_7_day_request():
    for training_days in range(1, 8):
        for squat in range(training_days + 1):
            for bench in range(training_days + 1):
                for deadlift in range(training_days + 1):
                    if squat + bench + deadlift < training_days:
                        continue
                    schedule = _day_sequence(
                        factory_request(training_days, squat, bench, deadlift)
                    )
                    assert len(schedule) == training_days
                    assert all(day and set(day) <= {"S", "B", "D"} for day in schedule)
                    assert [sum(code in day for day in schedule) for code in "SBD"] == [
                        squat, bench, deadlift,
                    ]


def test_six_day_golden_schedule_is_preserved_exactly():
    assert _day_sequence(factory_request(6, 2, 5, 2)) == [
        "B", "SD", "B", "B", "B", "SBD",
    ]


def test_six_day_bench_exposures_have_differentiated_coaching_intent():
    app = create_test_app()
    with app.app_context():
        days = _preview(factory_request(6, 2, 5, 2))
    bench = [
        exposure for day in days for exposure in day["exposures"]
        if exposure["lift_family"] == "bench"
    ]
    assert [item["role"] for item in bench] == [
        "primary_volume", "secondary_strength", "technique", "low_fatigue",
        "competition",
    ]
    assert len({item["exercise_name"] for item in bench}) == 5
    assert len({(item["sets"], item["reps"], item["rpe_offset"]) for item in bench}) == 5
    assert days[-1]["day_type"] == "SBD"
    assert {item["role"] for item in days[-1]["exposures"]} == {"competition"}


def test_multi_frequency_weekly_sets_are_allocated_deterministically_by_role():
    intents = [
        {"sets": 4, "role": "primary_volume"},
        {"sets": 3, "role": "secondary_strength"},
        {"sets": 2, "role": "competition"},
    ]

    allocation = _allocate_weekly_sets(8, intents)

    assert allocation == [3, 3, 2]
    assert sum(allocation) == 8
    assert all(value >= 1 for value in allocation)

def test_joint_constraints_select_supported_main_variations_and_coach_choice_wins():
    app = create_test_app()
    athlete_id = create_athlete(app)
    with app.app_context():
        existing = {row.name: row for row in Exercise.query.filter(Exercise.name.in_([
            "Competition Squat", "Competition Bench Press"
        ])).all()}
        for name, family, tags in (
            ("Competition Squat", "squat", '["hip_loading"]'),
            ("Competition Bench Press", "bench", '["shoulder_loading", "elbow_loading"]'),
        ):
            existing[name].lift_family = family
            existing[name].specificity = "competition"
            existing[name].constraint_tags = tags
        rows = [
            Exercise(name="Supported Squat", movement="squat", lift_family="squat", specificity="variation", constraint_tags="[]"),
            Exercise(name="Supported Bench", movement="press", lift_family="bench", specificity="variation", constraint_tags="[]"),
            Exercise(name="Conventional Deadlift", movement="hinge", lift_family="deadlift", specificity="competition", constraint_tags='["low_back_loading"]'),
            Exercise(name="Supported Deadlift", movement="hinge", lift_family="deadlift", specificity="variation", constraint_tags="[]"),
        ]
        db.session.add_all(rows)
        db.session.add_all([
            AthleteConstraintFlag(athlete_id=athlete_id, flag_kind="irritation", label=label, reported_by="athlete", starts_on=date.today())
            for label in ("Shoulder irritation", "Elbow irritation", "Hip irritation", "Low-back irritation")
        ])
        db.session.commit()

        preview = _preview(replace(factory_request(1, 1, 1, 1), athlete_id=athlete_id))
        assert preview[0]["exercises"][:3] == ["Supported Squat", "Supported Bench", "Supported Deadlift"]
        assert [item["exercise_name"] for item in preview[0]["exposures"]] == [
            "Supported Squat", "Supported Bench", "Supported Deadlift",
        ]
        assert not preview[0]["coach_review_required"]

        db.session.add(AthleteStateOverride(
            athlete_id=athlete_id, target_type="programming", target_ref="weekly",
            override_json={"exercise_selections": {"bench": "Competition Bench Press"}},
            reason="Coach selected tolerable bench setup", recorded_by="coach@example.com",
        ))
        db.session.commit()
        overridden = _preview(replace(factory_request(1, 1, 1, 1), athlete_id=athlete_id))
        assert overridden[0]["exercises"][1] == "Competition Bench Press"
        assert overridden[0]["exposures"][1]["exercise_name"] == "Competition Bench Press"
        assert overridden[0]["exposures"][1]["exercise_provenance"] == "coach_selected"


def test_no_compatible_main_exercise_requires_coach_review():
    app = create_test_app()
    athlete_id = create_athlete(app)
    with app.app_context():
        names = (
            "Competition Bench Press", "Close-Grip Bench Press",
            "Paused Bench Press", "Tempo Bench Press", "Feet-Up Bench Press",
        )
        existing = {row.name: row for row in Exercise.query.filter(Exercise.name.in_(names)).all()}
        for name in names:
            if name not in existing:
                existing[name] = Exercise(name=name, movement="press", active=True)
                db.session.add(existing[name])
        for row in existing.values():
            row.lift_family = "bench"
            row.constraint_tags = '["shoulder_loading"]'
        db.session.add(AthleteConstraintFlag(
            athlete_id=athlete_id, flag_kind="irritation",
            label="Shoulder irritation", reported_by="athlete",
            starts_on=date.today(),
        ))
        db.session.commit()

        preview = _preview(replace(factory_request(1, 0, 1, 0), athlete_id=athlete_id))

        assert preview[0]["coach_review_required"] is True
        assert "No automatically compatible bench alternative" in preview[0]["coach_review_reasons"][0]
        assert preview[0]["exposures"][0]["exercise_name"] == preview[0]["exercises"][0]
        assert preview[0]["exposures"][0]["exercise_provenance"] == "requires_coach_review"


@pytest.mark.parametrize(
    "training_days, squat, bench, deadlift, message",
    [
        (8, 1, 1, 1, "training days must be between 1 and 7"),
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
    assert b'min="1"' in response.data
    assert b'max="7"' in response.data


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
        assert sum(name == "Competition Squat" for name in exercise_names) == 1
        assert sum(name == "Competition Bench Press" for name in exercise_names) == 1
        assert sum(name == "Sumo Deadlift" for name in exercise_names) == 1
        assert {slot.exposure_role for session in first_week.sessions for slot in session.lift_slots} >= {
            "competition", "primary_volume", "secondary_strength",
        }
        bench_rows = [
            item for session in first_week.sessions for item in session.prescriptions
            if item.lift_slot is not None and item.lift_slot.lift_family == "bench"
        ]
        assert len({(item.exercise_name, item.sets, item.reps, item.rpe, item.notes)
                    for item in bench_rows}) == 3


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
        assert [item["name"] for item in automatic_accessories] == [
            "Development Row", "Coach Pin"
        ]
        suggested_accessory = automatic_accessories[0]
        assert suggested_accessory["source"] == "Library suggestion"
        assert any(
            "relevant to bench" in reason
            for reason in suggested_accessory["reasons"]
        )

        request = factory_request(3, 1, 1, 1)
        request = request.__class__(
            **{**request.__dict__, "accessory_exercise_ids": (pinned.id,)}
        )
        manual = _preview(request)
        assert [item["name"] for day in manual for item in day["accessories"]] == [
            "Coach Pin"
        ]
        assert all(day["accessory_outcome"] == "coach_selected" for day in manual)


def test_factory_automatic_falls_back_and_explains_zero_outcomes():
    app = create_test_app()
    with app.app_context():
        fallback = Exercise(
            name="Fallback Row", movement="accessory", category="balancing",
            accessory_suitable=True, auto_select=False,
            lift_relevance='["bench"]', fatigue_rating=3,
        )
        db.session.add(fallback)
        db.session.commit()

        automatic = _preview(factory_request(3, 1, 1, 1))
        selected = [item for day in automatic for item in day["accessories"]]
        assert [item["name"] for item in selected] == ["Fallback Row"]
        assert "eligible accessory fallback" in selected[0]["reasons"]
        assert any(
            day["accessory_outcome"] == "no_eligible_candidates"
            for day in automatic
        )

        intentional_none = _preview(replace(
            factory_request(3, 1, 1, 1), accessory_mode="none"
        ))
        assert all(not day["accessories"] for day in intentional_none)
        assert all(
            day["accessory_outcome"] == "intentional_none"
            for day in intentional_none
        )


def test_accessory_volume_produces_deterministic_default_metadata_recommendations():
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


def test_low_fatigue_metadata_justifies_more_than_three_accessories_per_session():
    app = create_test_app()
    with app.app_context():
        for index in range(9):
            db.session.add(Exercise(
                name=f"Low Cost Accessory {index:02d}", movement="accessory",
                category="assistance", accessory_suitable=True, auto_select=True,
                lift_relevance='["all"]', coach_priority=9 - index, fatigue_rating=1,
            ))
        db.session.commit()

        preview = _preview(replace(
            factory_request(3, 1, 1, 1), accessory_volume="high"
        ))

        assert preview[0]["accessory_count"] == 9
        assert preview[1]["accessory_count"] == 0
        assert [item["name"] for item in preview[0]["accessories"]] == [
            f"Low Cost Accessory {index:02d}" for index in range(9)
        ]


def test_more_than_three_manual_accessories_replace_automatic_selection():
    app = create_test_app()
    with app.app_context():
        automatic = Exercise(
            name="Automatic Row", movement="accessory", category="assistance",
            accessory_suitable=True, auto_select=True, lift_relevance='["all"]',
        )
        pinned = [
            Exercise(
                name=f"Coach Pin {index}", movement="accessory", category="assistance",
                accessory_suitable=True,
            )
            for index in range(7)
        ]
        db.session.add_all([automatic, *pinned])
        db.session.commit()

        preview = _preview(replace(
            factory_request(3, 1, 1, 1),
            accessory_exercise_ids=tuple(item.id for item in pinned),
        ))

        accessories = [item for day in preview for item in day["accessories"]]
        assert [item["name"] for item in accessories] == [
            "Coach Pin 0", "Coach Pin 3", "Coach Pin 6",
            "Coach Pin 1", "Coach Pin 4", "Coach Pin 2", "Coach Pin 5",
        ]
        assert all(item["provenance"] == "coach_selected" for item in accessories)
        assert "Automatic Row" not in {item["name"] for item in accessories}


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


def test_hook_grip_is_included_when_generic_grip_priority_is_none():
    app = create_test_app()
    with app.app_context():
        db.session.add(Exercise(
            name="Hook-Grip Practice Hold", movement="accessory", category="grip",
            accessory_suitable=True, auto_select=True,
            lift_relevance='["deadlift"]', coach_priority=10, fatigue_rating=1,
        ))
        db.session.commit()
        preview = _preview(replace(
            factory_request(3, 1, 1, 1), accessory_volume="low",
            deadlift_grip="hook", grip_work_priority="none",
        ))
        deadlift_day = next(day for day in preview if "D" in day["day_type"])
        assert [item["name"] for item in deadlift_day["accessories"]] == [
            "Hook-Grip Practice Hold",
        ]
        assert "hook-grip competition requirement" in deadlift_day["accessories"][0]["reasons"]


def test_non_hook_grip_remains_excluded_when_priority_is_none():
    app = create_test_app()
    with app.app_context():
        db.session.add(Exercise(
            name="Hook-Grip Practice Hold", movement="accessory", category="grip",
            accessory_suitable=True, auto_select=True,
            lift_relevance='["deadlift"]', coach_priority=10, fatigue_rating=1,
        ))
        db.session.commit()
        preview = _preview(replace(
            factory_request(3, 1, 1, 1), accessory_volume="low",
            deadlift_grip="mixed", grip_work_priority="none",
        ))
        assert "Hook-Grip Practice Hold" not in {
            item["name"] for day in preview for item in day["accessories"]
        }


def test_manual_atlas_stones_specialty_selection_is_preserved_exactly():
    app = create_test_app()
    athlete_id = create_athlete(app)
    with app.app_context():
        atlas = Exercise(
            name="Atlas Stones", movement="accessory", category="specialty",
            accessory_suitable=True, auto_select=False, default_sets=5,
            default_reps="3",
        )
        db.session.add(atlas)
        db.session.commit()
        atlas_id = atlas.id
    preview_response, accepted = preview_and_accept(app.test_client(), {
        **base_form(athlete_id), "name": "Specialty block",
        "accessory_exercise_id": str(atlas_id),
    })
    assert accepted.status_code == 302
    assert b"Atlas Stones" in preview_response.data
    with app.app_context():
        prescription = next(
            item for session in TrainingBlock.query.one().weeks[0].sessions
            for item in session.prescriptions if item.exercise_name == "Atlas Stones"
        )
        assert (prescription.provenance, prescription.sets, prescription.reps) == (
            "coach_selected", 5, "3",
        )


def test_automatic_assistance_never_selects_specialty_exercises():
    app = create_test_app()
    with app.app_context():
        db.session.add_all([
            Exercise(
                name="Atlas Stones", movement="accessory", category="specialty",
                accessory_suitable=True, auto_select=True, coach_priority=100,
                lift_relevance='["all"]', fatigue_rating=1,
            ),
            Exercise(
                name="Powerlifting Row", movement="accessory", category="assistance",
                accessory_suitable=True, auto_select=True, coach_priority=1,
                lift_relevance='["all"]', fatigue_rating=1,
            ),
        ])
        db.session.commit()
        preview = _preview(factory_request(3, 1, 1, 1))
    names = {item["name"] for day in preview for item in day["accessories"]}
    assert "Atlas Stones" not in names
    assert "Powerlifting Row" in names


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


def _fatigue_signal(value):
    return [SignalDraft("reported_fatigue", value, ("weekly_checkin:1",), "reported")]


def test_low_recovery_has_bounded_volume_and_rpe_effect(monkeypatch):
    app = create_test_app()
    athlete_id = create_athlete(app)
    monkeypatch.setattr(
        "portal.services.weekly_programming_intelligence.calculate_signals",
        lambda athlete: [SignalDraft("reported_recovery", 2, ("weekly_checkin:1",), "reported")],
    )
    response = app.test_client().post(
        "/programming/factory/preview", data={**base_form(athlete_id), "goal": "strength"}
    )
    assert response.status_code == 200
    with app.app_context():
        week = AthleteStateRecommendation.query.one().recommendation_json["volume_progression"]["weeks"][0]
        assert week["sbd_sets"] == {"squat": 4, "bench": 4, "deadlift": 4}
        assert week["target_rpe"] == 6.5


def test_low_rpe_adherence_caps_rpe_without_cutting_volume(monkeypatch):
    app = create_test_app()
    athlete_id = create_athlete(app)
    monkeypatch.setattr(
        "portal.services.weekly_programming_intelligence.calculate_signals",
        lambda athlete: [SignalDraft("rpe_adherence_rate", 0.5, ("training_log:1",), "calculated")],
    )
    response = app.test_client().post(
        "/programming/factory/preview",
        data={**base_form(athlete_id), "goal": "strength", "week_count": "4"},
    )
    assert response.status_code == 200
    with app.app_context():
        weeks = AthleteStateRecommendation.query.one().recommendation_json["volume_progression"]["weeks"]
        assert max(week["target_rpe"] for week in weeks) == 7.5
        assert weeks[0]["sbd_sets"] == {"squat": 4, "bench": 4, "deadlift": 4}


def test_coach_rpe_cap_overrides_derived_readiness_cap(monkeypatch):
    app = create_test_app()
    athlete_id = create_athlete(app)
    monkeypatch.setattr(
        "portal.services.weekly_programming_intelligence.calculate_signals",
        lambda athlete: _fatigue_signal(9),
    )
    with app.app_context():
        db.session.add(AthleteStateOverride(
            athlete_id=athlete_id, target_type="programming", target_ref="weekly",
            override_json={"rpe_cap": 8.5}, reason="Coach reviewed readiness",
            recorded_by="coach@example.com",
        ))
        db.session.commit()
    response = app.test_client().post(
        "/programming/factory/preview",
        data={**base_form(athlete_id), "goal": "strength", "week_count": "4"},
    )
    assert response.status_code == 200
    with app.app_context():
        weeks = AthleteStateRecommendation.query.one().recommendation_json["volume_progression"]["weeks"]
        assert max(week["target_rpe"] for week in weeks) == 8.0
        assert "RPE cap 8.5: Coach reviewed readiness" in AthleteStateRecommendation.query.one().recommendation_json["volume_progression"]["overrides_applied"]


def test_high_fatigue_exactly_reduces_preview_and_persisted_sets_within_bounds(monkeypatch):
    app = create_test_app()
    athlete_id = create_athlete(app)
    monkeypatch.setattr(
        "portal.services.weekly_programming_intelligence.calculate_signals",
        lambda athlete: _fatigue_signal(9),
    )
    preview_response, accepted = preview_and_accept(
        app.test_client(), base_form(athlete_id)
    )
    assert accepted.status_code == 302
    assert b"bounded 0.8 volume multiplier" in preview_response.data
    assert b"This remains a reviewable proposal until you accept it." in preview_response.data
    with app.app_context():
        proposal = AthleteStateRecommendation.query.one().recommendation_json
        assert proposal["volume_progression"]["weeks"][0]["sbd_sets"] == {
            "squat": 2, "bench": 2, "deadlift": 2,
        }
        totals = {"squat": 0, "bench": 0, "deadlift": 0}
        for session in TrainingBlock.query.one().weeks[0].sessions:
            for item in session.prescriptions:
                if item.lift_slot is not None:
                    totals[item.lift_slot.lift_family] += item.sets
        assert totals == {"squat": 2, "bench": 2, "deadlift": 2}
        assert all(item.sets >= 1 for session in TrainingBlock.query.one().weeks[0].sessions for item in session.prescriptions if item.lift_slot is not None)


def test_six_day_bench_sets_respect_authoritative_weekly_envelope():
    app = create_test_app()
    athlete_id = create_athlete(app)
    form = {
        **base_form(athlete_id), "training_days": "6",
        "squat_frequency": "2", "bench_frequency": "5",
        "deadlift_frequency": "2",
    }

    _preview_response, accepted = preview_and_accept(app.test_client(), form)

    assert accepted.status_code == 302
    with app.app_context():
        proposal = AthleteStateRecommendation.query.one().recommendation_json
        expected = proposal["volume_progression"]["weeks"][0]["sbd_sets"]["bench"]
        bench = [
            item for session in TrainingBlock.query.one().weeks[0].sessions
            for item in session.prescriptions
            if item.lift_slot is not None and item.lift_slot.lift_family == "bench"
        ]
        assert len(bench) == 5
        assert sum(item.sets for item in bench) == expected
        assert len({item.sets for item in bench}) > 1


def test_fatigue_reduction_persists_across_multi_exposure_lifts(monkeypatch):
    app = create_test_app()
    athlete_id = create_athlete(app)
    monkeypatch.setattr(
        "portal.services.weekly_programming_intelligence.calculate_signals",
        lambda athlete: _fatigue_signal(9),
    )
    form = {
        **base_form(athlete_id), "squat_frequency": "2",
        "bench_frequency": "3", "deadlift_frequency": "1",
    }

    _preview_response, accepted = preview_and_accept(app.test_client(), form)

    assert accepted.status_code == 302
    with app.app_context():
        expected = AthleteStateRecommendation.query.one().recommendation_json[
            "volume_progression"
        ]["weeks"][0]["sbd_sets"]
        actual = {family: 0 for family in expected}
        for session in TrainingBlock.query.one().weeks[0].sessions:
            for item in session.prescriptions:
                if item.lift_slot is not None:
                    actual[item.lift_slot.lift_family] += item.sets
        assert actual == expected


def test_coach_fixed_weekly_sets_persist_across_multi_exposure_lifts(monkeypatch):
    app = create_test_app()
    athlete_id = create_athlete(app)
    monkeypatch.setattr(
        "portal.services.weekly_programming_intelligence.calculate_signals",
        lambda athlete: _fatigue_signal(9),
    )
    with app.app_context():
        db.session.add(AthleteStateOverride(
            athlete_id=athlete_id, target_type="programming", target_ref="weekly",
            override_json={"weekly_sbd_sets": {
                "squat": 7, "bench": 10, "deadlift": 4,
            }},
            reason="Coach fixed weekly workload", recorded_by="coach@example.com",
        ))
        db.session.commit()
    form = {
        **base_form(athlete_id), "squat_frequency": "2",
        "bench_frequency": "3", "deadlift_frequency": "1",
    }

    _preview_response, accepted = preview_and_accept(app.test_client(), form)

    assert accepted.status_code == 302
    with app.app_context():
        actual = {"squat": 0, "bench": 0, "deadlift": 0}
        for session in TrainingBlock.query.one().weeks[0].sessions:
            for item in session.prescriptions:
                if item.lift_slot is not None:
                    actual[item.lift_slot.lift_family] += item.sets
        assert actual == {"squat": 7, "bench": 10, "deadlift": 4}


def test_final_rpe_cap_is_applied_after_exposure_role_offsets(monkeypatch):
    app = create_test_app()
    athlete_id = create_athlete(app)
    monkeypatch.setattr(
        "portal.services.weekly_programming_intelligence.calculate_signals",
        lambda athlete: _fatigue_signal(9),
    )
    form = {
        **base_form(athlete_id), "goal": "peaking",
        "squat_frequency": "2", "bench_frequency": "3",
        "deadlift_frequency": "1",
    }

    _preview_response, accepted = preview_and_accept(app.test_client(), form)

    assert accepted.status_code == 302
    with app.app_context():
        rpes = [
            item.rpe for session in TrainingBlock.query.one().weeks[0].sessions
            for item in session.prescriptions if item.lift_slot is not None
        ]
        assert max(rpes) == 7
        assert len(set(rpes)) > 1


@pytest.mark.parametrize("fatigue", [None, 7])
def test_missing_or_baseline_fatigue_does_not_change_exact_output(monkeypatch, fatigue):
    app = create_test_app()
    athlete_id = create_athlete(app)
    monkeypatch.setattr(
        "portal.services.weekly_programming_intelligence.calculate_signals",
        lambda athlete: [] if fatigue is None else _fatigue_signal(fatigue),
    )
    response = app.test_client().post(
        "/programming/factory/preview", data=base_form(athlete_id)
    )
    assert response.status_code == 200
    with app.app_context():
        week = AthleteStateRecommendation.query.one().recommendation_json[
            "volume_progression"
        ]["weeks"][0]
        assert week["sbd_sets"] == {"squat": 3, "bench": 3, "deadlift": 3}
        assert week["sbd_range"] == {
            "squat": [2, 4], "bench": [2, 4], "deadlift": [2, 4],
        }


def test_explicit_coach_volume_override_wins_over_high_fatigue(monkeypatch):
    app = create_test_app()
    athlete_id = create_athlete(app)
    monkeypatch.setattr(
        "portal.services.weekly_programming_intelligence.calculate_signals",
        lambda athlete: _fatigue_signal(9),
    )
    with app.app_context():
        db.session.add(AthleteStateOverride(
            athlete_id=athlete_id, target_type="programming", target_ref="weekly",
            override_json={"weekly_sbd_sets": {
                "squat": 4, "bench": 4, "deadlift": 4,
            }},
            reason="Coach observed full recovery", recorded_by="coach@example.com",
        ))
        db.session.commit()
    response = app.test_client().post(
        "/programming/factory/preview", data=base_form(athlete_id)
    )
    assert response.status_code == 200
    with app.app_context():
        volume = AthleteStateRecommendation.query.one().recommendation_json[
            "volume_progression"
        ]
        assert volume["weeks"][0]["sbd_sets"] == {
            "squat": 4, "bench": 4, "deadlift": 4,
        }
        assert volume["overrides_applied"][-3:] == [
            "Squat set target 4: Coach observed full recovery",
            "Bench set target 4: Coach observed full recovery",
            "Deadlift set target 4: Coach observed full recovery",
        ]


def test_reviewed_volume_proposal_is_stored_and_allocated_only_on_acceptance():
    app = create_test_app()
    athlete_id = create_athlete(app)
    client = app.test_client()
    response = client.post(
        "/programming/factory/preview",
        data={
            **base_form(athlete_id),
            "week_count": 4,
            "goal": "peaking",
            "meet_date": "2026-10-24",
        },
    )
    assert response.status_code == 200
    assert b"Volume progression proposal" in response.data
    assert b"Taper" in response.data
    with app.app_context():
        assert TrainingBlock.query.count() == 0
        stored = AthleteStateRecommendation.query.one().recommendation_json
        assert stored["volume_progression"]["weeks"][-1]["phase"] == "taper"

    accepted = client.post("/programming/factory", data=preview_fields(response))
    assert accepted.status_code == 302
    with app.app_context():
        block = TrainingBlock.query.one()
        final_week = block.weeks[-1]
        totals = {"squat": 0, "bench": 0, "deadlift": 0}
        for session in final_week.sessions:
            for item in session.prescriptions:
                if item.lift_slot is not None:
                    totals[item.lift_slot.lift_family] += item.sets
        assert totals == {"squat": 1, "bench": 1, "deadlift": 1}


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


def test_factory_composes_general_and_targeted_sbd_warmups():
    app = create_test_app()
    athlete_id = create_athlete(app)
    client = app.test_client()
    response, accepted = preview_and_accept(client, base_form(athlete_id))
    assert response.status_code == 200
    assert accepted.status_code == 302
    with app.app_context():
        block = TrainingBlock.query.one()
        for session in block.weeks[0].sessions:
            assignments = WarmupAssignment.query.filter_by(session_id=session.id).all()
            general = [item for item in assignments if item.lift_slot_id is None]
            targeted = [item for item in assignments if item.lift_slot_id is not None]
            assert [item.protocol.stable_key for item in general] == ["factory-session-general"]
            assert {item.lift_slot_id for item in targeted} == {
                slot.id for slot in session.lift_slots
            }
            assert {item.protocol.stable_key for item in targeted} == {
                f"factory-{slot.lift_family}" for slot in session.lift_slots
            }


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
