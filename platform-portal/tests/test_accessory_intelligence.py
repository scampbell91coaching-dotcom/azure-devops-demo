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

        assert AccessoryIntelligence().candidates(
            phase="development",
            lift_families={"squat"},
            excluded_constraint_tags={"knee_flexion"},
        ) == []


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
