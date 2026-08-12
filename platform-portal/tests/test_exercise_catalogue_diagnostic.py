from portal import create_app
from portal.extensions import db
from portal.models.exercise_library import Exercise
from portal.services.exercise_catalogue_diagnostic import (
    build_exercise_catalogue_diagnostic,
)


def test_diagnostic_reports_selection_counts_metadata_and_inconsistencies():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        Exercise.query.delete()
        db.session.add_all([
            Exercise(
                name="Ready Row", movement="accessory", category="back",
                accessory_suitable=True, auto_select=True, fatigue_rating=2,
                equipment_options='["cable"]', constraint_tags="[]",
                lift_relevance='["bench"]', training_phases='["development"]',
                compatibility_tags='["commercial_gym"]',
            ),
            Exercise(
                name="Manual Row", movement="accessory", category="back",
                accessory_suitable=True, auto_select=False, fatigue_rating=8,
            ),
            Exercise(
                name="Blocked Auto Row", movement="warmup", category="competition",
                accessory_suitable=False, auto_select=True,
                lift_relevance="not-json", constraint_tags='[""]',
            ),
            Exercise(
                name="Inactive Row", movement="accessory", category="back",
                accessory_suitable=True, auto_select=True, active=False,
            ),
        ])
        db.session.commit()

        report = build_exercise_catalogue_diagnostic(Exercise.query.all())

    assert report["counts"] == {
        "active": 3,
        "accessory_suitable": 2,
        "auto_select": 2,
        "automatic_selection_eligible": 1,
        "accessory_suitable_not_auto_select": 1,
    }
    assert [item["name"] for item in report["fatigue_cost_issues"]] == ["Manual Row"]
    assert report["accessory_metadata_coverage"]["equipment_options"] == {
        "populated": 1, "empty": 0, "missing": 1, "invalid": 0,
    }
    blocked = next(
        item for item in report["category_movement_inconsistencies"]
        if item["name"] == "Blocked Auto Row"
    )
    assert "auto_select is blocked because accessory_suitable is false" in blocked["reasons"]
    assert "lift_relevance is invalid JSON-list metadata" in blocked["reasons"]


def test_audit_command_is_read_only_and_emits_json():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        Exercise.query.delete()
        db.session.add(Exercise(
            name="Audit Me", movement="accessory", category="back",
            accessory_suitable=True, auto_select=False,
        ))
        db.session.commit()

    result = app.test_cli_runner().invoke(args=["audit-exercise-catalogue"])

    assert result.exit_code == 0
    assert '"accessory_suitable_not_auto_select": 1' in result.output
    with app.app_context():
        assert Exercise.query.count() == 1
