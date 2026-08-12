from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for

from .auth import roles_required
from .extensions import db
from .models.athlete import Athlete
from .models.user import UserRole
from .repositories.nutrition_prescriptions import SqlAlchemyMacroPrescriptionRepository
from .repositories.meal_plans import SqlAlchemyMealPlanRepository
from .services.client_service_profiles import Service
from .services.client_services import may_start_client_service
from .services.meal_plans import DayMode, DraftStatus, FoodSnapshot, MacroTotals, Meal, MealItem, MealPlanDay, MealPlanDraft, MealPlanWorkflow, PrescriptionSnapshot, PublicationError, WorkflowConflictError
from .services.nutrition_prescriptions import MacroPrescriptionService
from .tenancy import coach_owns_athlete, owned_athlete_ids, require_tenancy_context

meal_plan_delivery_bp = Blueprint("meal_plan_delivery", __name__)


def _workflow() -> MealPlanWorkflow:
    workflow = current_app.extensions.get("meal_plan_workflow")
    if not isinstance(workflow, MealPlanWorkflow):
        abort(503, description="Meal-plan delivery is not configured.")
    return workflow


def _draft(template_id: str, *, editable: bool = False) -> MealPlanDraft:
    require_tenancy_context()
    draft = _workflow().repository.get_draft(template_id)
    if draft is None:
        abort(404)
    user = g.get("current_user")
    if user is not None and draft.coach_id != str(user.id):
        abort(404)
    if editable and draft.status is not DraftStatus.DRAFT:
        abort(409, description="Published revisions cannot be edited. Create a revision first.")
    return draft


def _save(original: MealPlanDraft, revised: MealPlanDraft):
    _workflow().save_draft(revised, expected_revision=original.revision)
    db.session.commit()


def _number(name: str, *, positive: bool = False) -> Decimal:
    try:
        value = Decimal(request.form.get(name, "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError(f"Enter a valid {name.replace('_', ' ')}.")
    if value < 0 or (positive and value <= 0):
        raise ValueError(f"{name.replace('_', ' ').title()} must be {'positive' if positive else 'zero or greater'}.")
    return value


@meal_plan_delivery_bp.get("/coach/meal-plans")
@roles_required(UserRole.COACH)
def coach_index():
    require_tenancy_context()
    repository = _workflow().repository
    if isinstance(repository, SqlAlchemyMealPlanRepository):
        drafts = repository.list_drafts(g.current_user.id)
    elif hasattr(repository, "list_drafts"):
        drafts = tuple(
            draft
            for draft in repository.list_drafts()
            if draft.coach_id == str(g.current_user.id)
        )
    else:
        drafts = ()
    athlete_ids = owned_athlete_ids(g.current_user.id)
    if isinstance(repository, SqlAlchemyMealPlanRepository):
        assignments = repository.list_assignments(athlete_ids)
    elif hasattr(repository, "list_assignments"):
        assignments = tuple(
            item
            for item in repository.list_assignments()
            if item.athlete_id in athlete_ids
        )
    else:
        assignments = ()
    return render_template("meal_plans/coach_index.html", drafts=drafts, assignments=assignments)


@meal_plan_delivery_bp.post("/coach/meal-plans")
@roles_required(UserRole.COACH)
def create_template():
    require_tenancy_context()
    name = request.form.get("name", "").strip()
    if not name:
        abort(400, description="Meal-plan name is required.")
    draft = MealPlanDraft(str(uuid4()), 1, str(g.current_user.id), name, notes=request.form.get("notes", "").strip() or None)
    _workflow().save_draft(draft)
    db.session.commit()
    return redirect(url_for("meal_plan_delivery.edit_template", template_id=draft.template_id))


@meal_plan_delivery_bp.get("/coach/meal-plans/<template_id>/edit")
@roles_required(UserRole.COACH)
def edit_template(template_id: str):
    return render_template("meal_plans/coach_edit.html", draft=_draft(template_id))


@meal_plan_delivery_bp.post("/coach/meal-plans/<template_id>/days")
@roles_required(UserRole.COACH)
def add_day(template_id: str):
    draft = _draft(template_id, editable=True)
    name = request.form.get("name", "").strip()
    try:
        mode = DayMode(request.form.get("mode", "fixed"))
        flexible = MacroTotals(*(_number(name) for name in ("calories", "protein_g", "carbohydrate_g", "fat_g", "fibre_g"))) if mode is not DayMode.FIXED else MacroTotals()
        revised = _workflow().add_day(draft, MealPlanDay(str(uuid4()), name, len(draft.days) + 1, mode, flexible_target=flexible))
        _save(draft, revised)
    except ValueError as exc:
        db.session.rollback(); abort(400, description=str(exc))
    return redirect(url_for("meal_plan_delivery.edit_template", template_id=template_id))


@meal_plan_delivery_bp.post("/coach/meal-plans/<template_id>/days/<day_id>/meals")
@roles_required(UserRole.COACH)
def add_meal(template_id: str, day_id: str):
    draft = _draft(template_id, editable=True)
    day = next((item for item in draft.days if item.day_id == day_id), None)
    if day is None: abort(404)
    try:
        revised = _workflow().add_meal(draft, day_id, Meal(str(uuid4()), request.form.get("name", "").strip(), len(day.meals) + 1, (), request.form.get("note", "").strip() or None))
        _save(draft, revised)
    except ValueError as exc:
        db.session.rollback(); abort(400, description=str(exc))
    return redirect(url_for("meal_plan_delivery.edit_template", template_id=template_id))


@meal_plan_delivery_bp.post("/coach/meal-plans/<template_id>/meals/<meal_id>/items")
@roles_required(UserRole.COACH)
def add_item(template_id: str, meal_id: str):
    draft = _draft(template_id, editable=True)
    try:
        food = FoodSnapshot(str(uuid4()), request.form.get("name", "").strip(), _number("reference_amount", positive=True), request.form.get("unit", "").strip(), MacroTotals(*(_number(name) for name in ("calories", "protein_g", "carbohydrate_g", "fat_g", "fibre_g"))))
        item = MealItem(str(uuid4()), food, _number("amount", positive=True), request.form.get("note", "").strip() or None)
        revised = _workflow().add_item(draft, meal_id, item)
        _save(draft, revised)
    except ValueError as exc:
        db.session.rollback(); abort(400, description=str(exc))
    return redirect(url_for("meal_plan_delivery.edit_template", template_id=template_id))


@meal_plan_delivery_bp.post("/coach/meal-plans/<template_id>/items/<item_id>")
@roles_required(UserRole.COACH)
def edit_item(template_id: str, item_id: str):
    draft = _draft(template_id, editable=True)
    try:
        revised = _workflow().set_portion(draft, item_id, _number("amount", positive=True))
        _save(draft, revised)
    except ValueError as exc:
        db.session.rollback(); abort(400, description=str(exc))
    return redirect(url_for("meal_plan_delivery.edit_template", template_id=template_id))


def _prescription(athlete_id: int, on_date: date) -> PrescriptionSnapshot | None:
    item = MacroPrescriptionService(SqlAlchemyMacroPrescriptionRepository()).prescription_on(athlete_id, on_date)
    if item is None: return None
    targets = item.daily_targets
    return PrescriptionSnapshot(item.prescription_id, 1, MacroTotals(targets.calories, targets.protein_g, targets.carbohydrate_g, targets.fat_g, targets.fibre_g or 0))


@meal_plan_delivery_bp.get("/coach/meal-plan-templates/<template_id>/preview")
@roles_required(UserRole.COACH)
def coach_preview(template_id: str):
    draft = _draft(template_id)
    athlete_id = request.args.get("athlete_id", type=int)
    effective = request.args.get("effective_from", type=date.fromisoformat) or datetime.now(UTC).date()
    if athlete_id and not coach_owns_athlete(g.current_user.id, athlete_id):
        abort(404)
    athlete = db.session.get(Athlete, athlete_id) if athlete_id else None
    prescription = _prescription(athlete_id, effective) if athlete_id else None
    preview = _workflow().preview(draft, prescription) if prescription else None
    athlete_ids = owned_athlete_ids(g.current_user.id)
    athletes = (
        Athlete.query.filter(Athlete.id.in_(athlete_ids))
        .order_by(Athlete.last_name, Athlete.first_name)
        .all()
        if athlete_ids
        else []
    )
    return render_template("meal_plans/coach_preview.html", draft=draft, athlete=athlete, athletes=athletes, effective_from=effective, prescription=prescription, preview=preview, entitled=bool(athlete_id and may_start_client_service(athlete_id, Service.NUTRITION_COACHING)))


@meal_plan_delivery_bp.post("/coach/meal-plan-templates/<template_id>/publish")
@roles_required(UserRole.COACH)
def publish(template_id: str):
    draft = _draft(template_id, editable=True)
    try:
        athlete_id = int(request.form["athlete_id"])
        if not coach_owns_athlete(g.current_user.id, athlete_id):
            abort(404)
        effective = date.fromisoformat(request.form["effective_from"])
        until_raw = request.form.get("effective_until", "").strip()
        prescription = _prescription(athlete_id, effective)
        if prescription is None: raise PublicationError("No nutrition targets apply on the assignment start date.")
        assignment = _workflow().publish(assignment_id=str(uuid4()), athlete_id=athlete_id, draft=draft, prescription=prescription, effective_from=effective, effective_until=date.fromisoformat(until_raw) if until_raw else None, actor_id=str(g.current_user.id), override_reason=request.form.get("override_reason", "").strip() or None)
        db.session.commit()
    except (ValueError, KeyError, PublicationError, WorkflowConflictError, PermissionError) as exc:
        db.session.rollback(); abort(400, description=str(exc))
    flash("Meal plan published and assigned.", "success")
    return redirect(url_for("meal_plan_delivery.coach_assignment", assignment_id=assignment.assignment_id))


@meal_plan_delivery_bp.post("/coach/meal-plan-templates/<template_id>/revise")
@roles_required(UserRole.COACH)
def revise(template_id: str):
    draft = _draft(template_id)
    if draft.status is not DraftStatus.PUBLISHED: abort(409)
    revised = replace(draft, revision=draft.revision + 1, status=DraftStatus.DRAFT)
    _workflow().repository.save_draft(revised, expected_revision=draft.revision)
    db.session.commit()
    return redirect(url_for("meal_plan_delivery.edit_template", template_id=template_id))


@meal_plan_delivery_bp.get("/coach/meal-plan-assignments/<assignment_id>")
@roles_required(UserRole.COACH)
def coach_assignment(assignment_id: str):
    assignment = _workflow().repository.get_assignment(assignment_id)
    if assignment is None or not coach_owns_athlete(
        g.current_user.id, assignment.athlete_id
    ):
        abort(404)
    return render_template("meal_plans/athlete_view.html", assignment=assignment, coach_view=True)


def _athlete_id():
    user = g.get("current_user")
    value = getattr(user, "athlete_id", None) if user is not None else session.get("athlete_id")
    if isinstance(value, bool) or not isinstance(value, int): abort(401)
    return value


@meal_plan_delivery_bp.get("/athlete/meal-plan")
def athlete_plan():
    athlete_id = _athlete_id()
    assignment = _workflow().current_for_athlete(athlete_id, datetime.now(UTC).date())
    if assignment is None: abort(404)
    return render_template("meal_plans/athlete_view.html", assignment=assignment, coach_view=False, history=_workflow().historical_for_athlete(athlete_id))


@meal_plan_delivery_bp.get("/athlete/meal-plan/history/<assignment_id>")
def athlete_historical_plan(assignment_id: str):
    athlete_id = _athlete_id()
    assignment = _workflow().repository.get_assignment(assignment_id)
    if assignment is None or assignment.athlete_id != athlete_id: abort(404)
    return render_template("meal_plans/athlete_view.html", assignment=assignment, coach_view=False, historical=True, history=_workflow().historical_for_athlete(athlete_id))
