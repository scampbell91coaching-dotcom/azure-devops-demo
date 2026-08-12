from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import roles_required
from .extensions import db
from .models.user import UserRole
from .repositories.nutrition_prescriptions import SqlAlchemyMacroPrescriptionRepository
from .services.client_service_profiles import Service
from .services.client_services import may_start_client_service
from .services.nutrition_prescriptions import MacroPrescription, MacroPrescriptionService, MacroTargets, PrescriptionConflictError, PrescriptionProvenance
from .tenancy import require_athlete_access

nutrition_prescriptions_bp = Blueprint("nutrition_prescriptions", __name__)


def _service():
    return MacroPrescriptionService(SqlAlchemyMacroPrescriptionRepository())


def _targets(prefix: str = "") -> MacroTargets | None:
    names = ("calories", "protein_g", "carbohydrate_g", "fat_g")
    values = [request.form.get(prefix + name, "").strip() for name in names]
    fibre = request.form.get(prefix + "fibre_g", "").strip()
    if prefix and not any(values) and not fibre:
        return None
    if not all(values):
        raise ValueError("Calories, protein, carbohydrate and fat are required for each selected target set.")
    return MacroTargets(*(int(value) for value in values), int(fibre) if fibre else None)


@nutrition_prescriptions_bp.get("/athletes/<int:athlete_id>/nutrition-prescriptions")
@roles_required(UserRole.COACH)
def coach_index(athlete_id: int):
    athlete = require_athlete_access(athlete_id)
    today = datetime.now(UTC).date()
    service = _service()
    return render_template("nutrition_prescriptions/coach.html", athlete=athlete,
        entitled=may_start_client_service(athlete_id, Service.NUTRITION_COACHING),
        current=service.prescription_on(athlete_id, today), history=service.history(athlete_id),
        today=today, errors=(), form={})


@nutrition_prescriptions_bp.post("/athletes/<int:athlete_id>/nutrition-prescriptions")
@roles_required(UserRole.COACH)
def create(athlete_id: int):
    athlete = require_athlete_access(athlete_id)
    if not may_start_client_service(athlete_id, Service.NUTRITION_COACHING):
        abort(403, description="Nutrition coaching must be enabled before assigning targets.")
    try:
        effective_from = date.fromisoformat(request.form.get("effective_from", ""))
        until_value = request.form.get("effective_until", "").strip()
        notes = request.form.get("coach_notes", "").strip() or None
        prescription = MacroPrescription(
            prescription_id=str(uuid4()), athlete_id=athlete_id, daily_targets=_targets(),
            effective_from=effective_from, effective_until=date.fromisoformat(until_value) if until_value else None,
            training_day_targets=_targets("training_"), rest_day_targets=_targets("rest_"),
            meal_count=int(request.form["meal_count"]) if request.form.get("meal_count", "").strip() else None,
            notes=notes,
            provenance=PrescriptionProvenance(actor_id=str(g.current_user.id), actor_role="coach", recorded_at=datetime.now(UTC)),
        )
        _service().assign(prescription)
        db.session.commit()
    except (ValueError, TypeError, KeyError) as exc:
        db.session.rollback()
        abort(400, description=str(exc) or "Enter valid macro targets and effective dates.")
    flash("Nutrition targets assigned.", "success")
    return redirect(url_for("nutrition_prescriptions.coach_index", athlete_id=athlete_id))


@nutrition_prescriptions_bp.get("/athlete/nutrition-targets")
def athlete_current():
    user = g.get("current_user")
    athlete_id = getattr(user, "athlete_id", None)
    if not isinstance(athlete_id, int):
        abort(401)
    if not may_start_client_service(athlete_id, Service.NUTRITION_COACHING):
        abort(404)
    today = datetime.now(UTC).date()
    return render_template("nutrition_prescriptions/athlete.html", prescription=_service().prescription_on(athlete_id, today), today=today)
