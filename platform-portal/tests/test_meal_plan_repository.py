from dataclasses import replace
from datetime import UTC, date, datetime

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.user import User
from portal.repositories.meal_plans import SqlAlchemyMealPlanRepository
from portal.services.meal_plans import MacroTotals, MealPlanWorkflow, PrescriptionSnapshot
from test_meal_plan_workflow import plan


def test_database_repository_survives_app_restart_and_keeps_history_when_entitlement_ends(tmp_path):
    uri = f"sqlite:///{tmp_path / 'durable-meals.db'}"
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": uri})
    with app.app_context():
        athlete = Athlete(id=7, first_name="Alex", last_name="Stone", email="durable-athlete@example.test")
        coach = User(id=41, email="durable-coach@example.test", role="coach", active=True)
        db.session.add_all([athlete, coach]); db.session.commit()
        workflow = MealPlanWorkflow(SqlAlchemyMealPlanRepository(), lambda _: True)
        draft = replace(plan(), coach_id="41")
        workflow.save_draft(draft)
        assignment = workflow.publish(
            assignment_id="durable-assignment", athlete_id=7, draft=draft,
            prescription=PrescriptionSnapshot("target-snapshot", 2, MacroTotals(2000, 150, 250, 60, 25)),
            effective_from=date(2026, 8, 1), actor_id="41",
            now=datetime(2026, 8, 1, tzinfo=UTC),
        )
        db.session.commit()
        assert assignment.days[0].meals[0].items[0].food.name == "Rice"

    restarted = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": uri})
    with restarted.app_context():
        workflow = MealPlanWorkflow(SqlAlchemyMealPlanRepository(), lambda _: False)
        assert workflow.current_for_athlete(7, date(2026, 8, 11)) is None
        historical = workflow.historical_for_athlete(7)
        assert len(historical) == 1
        assert historical[0].template_name == "Performance plan"
        assert historical[0].prescription.prescription_id == "target-snapshot"
        assert historical[0].days[0].meals[0].items[0].food.facts_revision == "label-8"
