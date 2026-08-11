from __future__ import annotations

from datetime import UTC, date, datetime

from flask import Blueprint, abort, current_app, g, render_template, session

from .services.meal_plans import MealPlanWorkflow


meal_plan_delivery_bp = Blueprint("meal_plan_delivery", __name__)


def _workflow() -> MealPlanWorkflow:
    workflow = current_app.extensions.get("meal_plan_workflow")
    if not isinstance(workflow, MealPlanWorkflow):
        abort(503, description="Meal-plan delivery is not configured.")
    return workflow


@meal_plan_delivery_bp.get("/coach/meal-plan-templates/<template_id>/preview")
def coach_preview(template_id: str):
    draft = _workflow().repository.get_draft(template_id)
    if draft is None:
        abort(404)
    return render_template("meal_plans/coach_preview.html", draft=draft)


@meal_plan_delivery_bp.get("/athlete/meal-plan")
def athlete_plan():
    user = g.get("current_user")
    athlete_id = user.athlete_id if user is not None else session.get("athlete_id")
    if isinstance(athlete_id, bool) or not isinstance(athlete_id, int):
        abort(401)
    assignment = _workflow().current_for_athlete(athlete_id, datetime.now(UTC).date())
    if assignment is None:
        abort(404)
    return render_template("meal_plans/athlete_view.html", assignment=assignment)
