import json

from portal import create_app
from portal.extensions import db
from portal.models.exercise_library import Exercise
from portal.services.accessory_intelligence import (
    AccessoryIntelligence,
    AccessoryRankingContext,
)


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
        assert fallback == []


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


def test_auto_select_false_is_a_hard_automatic_exclusion():
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

        assert candidates == []


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


def test_ranked_candidates_explain_selection_and_every_exclusion_rule():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        rows = [
            Exercise(
                name="Observation Match", movement="accessory", category="assistance",
                active=True, accessory_suitable=True, auto_select=True,
                fatigue_rating=2, coach_priority=3,
                lift_relevance='["bench"]', training_phases='["hypertrophy"]',
                technical_purposes='["lockout"]', equipment_options='["cable"]',
            ),
            Exercise(
                name="Constraint Conflict", movement="accessory", category="assistance",
                active=True, accessory_suitable=True, auto_select=True,
                fatigue_rating=1, coach_priority=10, constraint_tags='["elbow_irritation"]',
            ),
            Exercise(
                name="Wrong Equipment", movement="accessory", category="assistance",
                active=True, accessory_suitable=True, auto_select=True,
                fatigue_rating=1, equipment_options='["machine"]',
            ),
            Exercise(
                name="Recently Used", movement="accessory", category="assistance",
                active=True, accessory_suitable=True, auto_select=True, fatigue_rating=1,
            ),
            Exercise(
                name="Disabled", movement="accessory", category="assistance",
                active=True, accessory_suitable=True, auto_select=False, fatigue_rating=1,
            ),
            Exercise(
                name="Inactive", movement="accessory", category="assistance",
                active=False, accessory_suitable=True, auto_select=True, fatigue_rating=1,
            ),
            Exercise(
                name="Unsuitable", movement="accessory", category="assistance",
                active=True, accessory_suitable=False, auto_select=True, fatigue_rating=1,
            ),
            Exercise(
                name="Wrong Context", movement="accessory", category="assistance",
                active=True, accessory_suitable=True, auto_select=True, fatigue_rating=1,
                lift_relevance='["squat"]', training_phases='["peaking"]',
            ),
            Exercise(
                name="Already Current", movement="accessory", category="assistance",
                active=True, accessory_suitable=True, auto_select=True, fatigue_rating=1,
            ),
        ]
        db.session.add_all(rows)
        db.session.commit()
        by_name = {row.name: row for row in rows}

        result = AccessoryIntelligence().ranked_candidates(AccessoryRankingContext(
            block_type="accumulation", goal="hypertrophy",
            session_lift_exposure=frozenset({"bench"}), fatigue_budget=2,
            athlete_constraint_tags=frozenset({"elbow_irritation"}),
            technical_observation_tags=frozenset({"lockout"}),
            available_equipment=frozenset({"cable"}),
            recent_exercise_ids=frozenset({by_name["Recently Used"].id}),
            current_exercise_ids=frozenset({by_name["Already Current"].id}),
        ))
        ranked = {item.exercise.name: item for item in result}

        assert ranked["Observation Match"].status == "selected"
        assert ranked["Observation Match"].fatigue_cost == 2
        assert "ATHLETE_TECHNICAL_OBSERVATION_MATCH" in ranked["Observation Match"].rule_ids
        assert "FATIGUE_BUDGET_SELECTED" in ranked["Observation Match"].rule_ids
        assert "ATHLETE_CONSTRAINT_EXCLUDED" in ranked["Constraint Conflict"].rule_ids
        assert "EQUIPMENT_UNAVAILABLE" in ranked["Wrong Equipment"].rule_ids
        assert "STATE_RECENTLY_USED" in ranked["Recently Used"].rule_ids
        assert "STATE_ALREADY_CURRENT" in ranked["Already Current"].rule_ids
        assert "META_NOT_ENABLED" in ranked["Disabled"].rule_ids
        assert "META_INACTIVE" in ranked["Inactive"].rule_ids
        assert "META_NOT_ACCESSORY_SUITABLE" in ranked["Unsuitable"].rule_ids
        assert "CONTEXT_BLOCK_GOAL_MISMATCH" in ranked["Wrong Context"].rule_ids
        assert "CONTEXT_LIFT_EXPOSURE_MISMATCH" in ranked["Wrong Context"].rule_ids
        assert all(item.reason and item.evidence for item in result)


def test_ranked_candidates_keep_pins_authoritative_and_have_no_count_ceiling():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        pinned = Exercise(
            name="Pinned Disabled Row", movement="accessory", category="assistance",
            active=False, accessory_suitable=False, auto_select=False, fatigue_rating=5,
        )
        automatic = [Exercise(
            name=f"Automatic {index:02d}", movement="accessory", category="assistance",
            active=True, accessory_suitable=True, auto_select=True,
            fatigue_rating=1, coach_priority=10 - index,
        ) for index in range(7)]
        db.session.add_all([pinned, *automatic])
        db.session.commit()

        result = AccessoryIntelligence().ranked_candidates(AccessoryRankingContext(
            block_type="development", goal="strength",
            session_lift_exposure=frozenset({"squat"}), fatigue_budget=7,
            pinned_exercise_ids=(pinned.id,),
        ))
        selected = [item for item in result if item.status == "selected"]

        assert selected[0].exercise.name == "Pinned Disabled Row"
        assert selected[0].rule_ids == ("PIN_AUTHORITATIVE",)
        assert len(selected) == 8
        assert sum(item.fatigue_cost for item in selected[1:]) == 7
        assert [item.exercise.name for item in selected[1:]] == [
            f"Automatic {index:02d}" for index in range(7)
        ]


def test_ranked_candidate_order_is_deterministic_with_budget_exclusions():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        db.session.add_all([
            Exercise(
                name=name, movement="accessory", category="assistance",
                active=True, accessory_suitable=True, auto_select=True,
                fatigue_rating=2, coach_priority=4,
            ) for name in ("Zulu", "Alpha", "Mike")
        ])
        db.session.commit()
        context = AccessoryRankingContext(
            block_type="strength", goal="strength",
            session_lift_exposure=frozenset({"deadlift"}), fatigue_budget=2,
        )
        intelligence = AccessoryIntelligence()

        first = intelligence.ranked_candidates(context)
        second = intelligence.ranked_candidates(context)

        assert [(item.exercise.name, item.status) for item in first] == [
            ("Alpha", "selected"), ("Mike", "excluded"), ("Zulu", "excluded")
        ]
        assert [(item.exercise.id, item.status, item.rule_ids) for item in first] == [
            (item.exercise.id, item.status, item.rule_ids) for item in second
        ]
        assert all(
            "FATIGUE_BUDGET_EXCEEDED" in item.rule_ids for item in first[1:]
        )
