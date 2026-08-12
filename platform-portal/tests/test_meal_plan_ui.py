from datetime import UTC, date, datetime
from decimal import Decimal
from dataclasses import replace
import time

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.user import User
from portal.services.meal_plans import MacroTotals, MealPlanWorkflow, InMemoryMealPlanRepository, PrescriptionSnapshot
from test_meal_plan_workflow import plan


def test_coach_preview_and_read_only_athlete_snapshot(tmp_path):
    app = create_app({"TESTING": True, "AUTHENTICATION_DISABLED": False, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'ui.db'}"})
    client = app.test_client()
    with app.app_context():
        athlete_row = Athlete(id=7, first_name="Alex", last_name="Stone", email="alex-meals@example.com")
        coach_user = User(email="coach-meals@example.com", role="coach", active=True)
        db.session.add_all([athlete_row, coach_user])
        db.session.flush()
        athlete_user = User(email="athlete-meals@example.com", role="athlete", athlete_id=7, active=True)
        db.session.add(athlete_user)
        db.session.commit()
        coach_id, athlete_user_id = coach_user.id, athlete_user.id
    repository = InMemoryMealPlanRepository()
    workflow = MealPlanWorkflow(repository, lambda _: True)
    draft = replace(plan(), coach_id=str(coach_id))
    workflow.save_draft(draft)
    workflow.publish(assignment_id="assignment-1", athlete_id=7, draft=draft, prescription=PrescriptionSnapshot("macro-1", 3, MacroTotals(2000, 150, 250, 60, 25)), effective_from=date(2020, 1, 1), actor_id="coach-1", now=datetime(2026, 8, 10, tzinfo=UTC))
    app.extensions["meal_plan_workflow"] = workflow

    with client.session_transaction() as auth_session:
        auth_session["user_id"] = coach_id
        auth_session["authenticated_at"] = time.time()
    coach = client.get("/coach/meal-plan-templates/template-1/preview")
    assert coach.status_code == 200
    assert b"Performance plan" in coach.data and b"Rice" in coach.data
    assert b"Assignment context" in coach.data
    assert b"Plan and target reconciliation" in coach.data
    assert b"Traditional Strength Platform" in coach.data

    with client.session_transaction() as session:
        session.clear()
        session["user_id"] = athlete_user_id
        session["authenticated_at"] = time.time()
        session["athlete_id"] = 7
    athlete = client.get("/athlete/meal-plan")
    assert athlete.status_code == 200
    assert b"prescription macro-1 revision 3" in athlete.data
    assert b"Save meal plan" not in athlete.data
    assert b"Potato" not in athlete.data


def test_coach_meal_plan_index_separates_templates_from_assignment_history(tmp_path):
    app = create_app({"TESTING": True, "AUTHENTICATION_DISABLED": False, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'index.db'}"})
    repository = InMemoryMealPlanRepository()
    app.extensions["meal_plan_workflow"] = MealPlanWorkflow(repository, lambda _: True)
    with app.app_context():
        coach_user = User(email="coach-index@example.com", role="coach", active=True)
        db.session.add(coach_user)
        db.session.commit()
        coach_id = coach_user.id
    client = app.test_client()
    with client.session_transaction() as auth_session:
        auth_session["user_id"] = coach_id
        auth_session["authenticated_at"] = time.time()

    response = client.get("/coach/meal-plans")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="templates"' in page
    assert 'id="assignment-history"' in page
    assert 'aria-controls="create-meal-plan"' in page
    assert "No meal plans yet. Create a template to begin." in page
