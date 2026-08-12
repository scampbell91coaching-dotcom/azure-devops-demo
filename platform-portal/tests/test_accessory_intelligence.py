import json

from portal import create_app
from portal.extensions import db
from portal.models.exercise_library import Exercise
from portal.services.accessory_intelligence import AccessoryIntelligence


def test_candidates_filter_and_explain_structured_metadata():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        db.session.add_all([
            Exercise(
                name="Paused Leg Press",
                movement="accessory",
                category="secondary strength",
                accessory_suitable=True,
                auto_select=True,
                lift_relevance=json.dumps(["squat"]),
                training_phases=json.dumps(["development"]),
                compatibility_tags=json.dumps(["commercial_gym"]),
                constraint_tags=json.dumps(["knee_flexion"]),
                coach_priority=8,
                fatigue_rating=3,
            ),
            Exercise(
                name="Legacy Row",
                movement="accessory",
                category="upper body",
                accessory_suitable=True,
                auto_select=False,
            ),
        ])
        db.session.commit()

        candidates = AccessoryIntelligence().candidates(
            phase="development",
            lift_families={"squat"},
            required_compatibility_tags={"commercial_gym"},
        )

        assert [item.exercise.name for item in candidates] == ["Paused Leg Press"]
        assert "relevant to squat" in candidates[0].reasons
        assert "suitable for development phase" in candidates[0].reasons

        fallback = AccessoryIntelligence().candidates(
            phase="development",
            lift_families={"squat"},
            excluded_constraint_tags={"knee_flexion"},
        )
        assert [item.exercise.name for item in fallback] == ["Legacy Row"]
        assert "eligible accessory fallback" in fallback[0].reasons


def test_candidates_are_ordered_by_coach_priority_then_fatigue_and_name():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        for name, priority, fatigue in (
            ("Lower priority", 1, 1),
            ("Higher fatigue", 5, 4),
            ("Lower fatigue", 5, 2),
        ):
            db.session.add(Exercise(
                name=name, movement="accessory", category="assistance",
                accessory_suitable=True, auto_select=True,
                coach_priority=priority, fatigue_rating=fatigue,
            ))
        db.session.commit()
        candidates = AccessoryIntelligence().candidates(
            phase="strength", lift_families={"bench"}
        )
        assert [item.exercise.name for item in candidates] == [
            "Lower fatigue", "Higher fatigue", "Lower priority"
        ]


def test_auto_select_is_preferred_but_eligible_rows_are_fallback_candidates():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        db.session.add_all([
            Exercise(
                name="Preferred but wrong lift", movement="accessory",
                accessory_suitable=True, auto_select=True,
                lift_relevance='["squat"]', coach_priority=1,
            ),
            Exercise(
                name="Eligible fallback", movement="accessory",
                accessory_suitable=True, auto_select=False,
                lift_relevance='["bench"]', coach_priority=10,
            ),
            Exercise(
                name="Inactive fallback", movement="accessory", active=False,
                accessory_suitable=True, auto_select=False,
                lift_relevance='["bench"]', coach_priority=20,
            ),
            Exercise(
                name="Unsuitable fallback", movement="accessory",
                accessory_suitable=False, auto_select=False,
                lift_relevance='["bench"]', coach_priority=20,
            ),
        ])
        db.session.commit()

        candidates = AccessoryIntelligence().candidates(
            phase="strength", lift_families={"bench"}
        )

        assert [item.exercise.name for item in candidates] == ["Eligible fallback"]
        assert "eligible accessory fallback" in candidates[0].reasons


def test_volume_policy_selects_six_plus_without_a_count_ceiling():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        for index in range(10):
            db.session.add(Exercise(
                name=f"Low Fatigue {index:02d}", movement="accessory",
                category="assistance", accessory_suitable=True, auto_select=True,
                lift_relevance='["bench"]', training_phases='["development"]',
                coach_priority=10 - index, fatigue_rating=1,
            ))
        db.session.commit()
        intelligence = AccessoryIntelligence()
        candidates = intelligence.candidates(
            phase="development", lift_families={"bench"}
        )

        selected = intelligence.select_for_volume(candidates, volume="high")

        assert len(selected) == 9
        assert [item.exercise.name for item in selected] == [
            f"Low Fatigue {index:02d}" for index in range(9)
        ]
        assert all("fits high fatigue budget (1/9)" in item.reasons for item in selected)


def test_volume_policy_keeps_phase_lift_compatibility_and_exclusions_authoritative():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        rows = [
            Exercise(
                name="Eligible", movement="accessory", category="assistance",
                accessory_suitable=True, auto_select=True, fatigue_rating=1,
                lift_relevance='["bench"]', training_phases='["strength"]',
                compatibility_tags='["home_gym"]',
            ),
            Exercise(
                name="Wrong Equipment", movement="accessory", category="assistance",
                accessory_suitable=True, auto_select=True, fatigue_rating=1,
                lift_relevance='["bench"]', training_phases='["strength"]',
                compatibility_tags='["commercial_gym"]',
            ),
            Exercise(
                name="Excluded", movement="accessory", category="assistance",
                accessory_suitable=True, auto_select=True, fatigue_rating=1,
                lift_relevance='["bench"]', training_phases='["strength"]',
                compatibility_tags='["home_gym"]', constraint_tags='["exclude_me"]',
            ),
        ]
        db.session.add_all(rows)
        db.session.commit()
        candidates = AccessoryIntelligence().candidates(
            phase="strength", lift_families={"bench"},
            required_compatibility_tags={"home_gym"},
            excluded_constraint_tags={"exclude_me"},
        )

        assert [item.exercise.name for item in candidates] == ["Eligible"]


def test_coach_can_configure_accessory_selection_metadata():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        exercise = Exercise(
            name="Configurable Row", movement="accessory", category="balancing"
        )
        db.session.add(exercise)
        db.session.commit()
        exercise_id = exercise.id

    response = app.test_client().post(
        f"/exercise-library/{exercise_id}/edit",
        data={
            "name": "Configurable Row",
            "movement": "accessory",
            "category": "balancing",
            "accessory_suitable": "on",
            "auto_select": "on",
            "lift_relevance": "Bench, all, bench",
            "training_phases": "Development",
            "compatibility_tags": "commercial_gym",
            "constraint_tags": "shoulder_loading",
            "coach_priority": "7",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        exercise = db.session.get(Exercise, exercise_id)
        assert exercise.auto_select is True
        assert exercise.lift_relevance == '["bench", "all"]'
        assert exercise.training_phases == '["development"]'
        assert exercise.coach_priority == 7


def test_grip_candidates_use_context_and_exclude_loaded_carry_shortcuts():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        db.session.add_all([
            Exercise(
                name="Double-Overhand Bar Hold", movement="accessory",
                category="grip", accessory_suitable=True, auto_select=True,
                lift_relevance='["deadlift"]', coach_priority=5,
            ),
            Exercise(
                name="Farmer's Carry", movement="accessory", category="grip",
                accessory_suitable=True, auto_select=True,
                lift_relevance='["deadlift"]', coach_priority=10,
                technical_purposes='["grip_strength"]',
            ),
        ])
        db.session.commit()

        candidates = AccessoryIntelligence().grip_candidates(
            phase="strength", competition_grip="mixed", strap_usage="some",
            priority="build",
        )

        assert [item.exercise.name for item in candidates] == [
            "Double-Overhand Bar Hold"
        ]
        assert "grip-work priority is build" in candidates[0].reasons
        assert "competition grip is mixed" in candidates[0].reasons
        assert any("training strap usage is some" in item for item in candidates[0].reasons)
        assert AccessoryIntelligence().grip_candidates(
            phase="strength", competition_grip="mixed", strap_usage="none",
            priority="none",
        ) == []
