from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, abort, current_app, g, jsonify, request, session
from werkzeug.exceptions import HTTPException

from ..extensions import db
from ..models.athlete import Athlete
from ..models.checkins import WeeklyCheckin
from ..models.programming import TrainingSession
from ..models.user import UserRole
from ..services.athlete_app_contract import (
    checkin_settings,
    checkins_dto,
    envelope,
    meal_plan_dto,
    programme_dto,
    progress_dto,
    session_dto,
    today_dto,
)
from ..services.checkins import validate_submission
from ..services.training_log import save_training_session

athlete_app_bp = Blueprint("athlete_app_api", __name__)


@athlete_app_bp.errorhandler(HTTPException)
def contract_error(error: HTTPException):
    return jsonify(
        envelope(
            {
                "error": {
                    "code": error.name.lower().replace(" ", "_"),
                    "message": error.description,
                }
            }
        )
    ), error.code


@athlete_app_bp.before_request
def require_athlete_identity() -> None:
    user = g.get("current_user")
    if user is not None and user.role != UserRole.ATHLETE:
        abort(403)
    if _athlete_id() is None:
        abort(401)


def _athlete_id() -> int | None:
    user = g.get("current_user")
    value = getattr(user, "athlete_id", None) if user is not None else None
    if current_app.config["AUTHENTICATION_DISABLED"] and value is None:
        value = session.get("athlete_id")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _json_object() -> dict:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        abort(400, description="Request body must be a JSON object.")
    return value


@athlete_app_bp.get("/today")
def today():
    data = today_dto(_athlete_id(), today=datetime.now(UTC).date())
    if data is None:
        abort(404)
    return jsonify(envelope(data))


@athlete_app_bp.get("/programme")
def programme():
    return jsonify(envelope(programme_dto(_athlete_id())))


@athlete_app_bp.get("/programme/sessions/<int:session_id>")
def session_detail(session_id: int):
    data = session_dto(_athlete_id(), session_id)
    if data is None:
        abort(404)
    return jsonify(envelope(data))


@athlete_app_bp.put("/programme/sessions/<int:session_id>/log")
def log_session(session_id: int):
    athlete_id = _athlete_id()
    training_session = db.session.get(TrainingSession, session_id)
    if (
        training_session is None
        or training_session.week.block.athlete_id != athlete_id
        or training_session.week.block.status != "active"
    ):
        abort(404)
    payload = _json_object()
    sets = payload.get("sets")
    if not isinstance(sets, list):
        abort(400, description="sets must be an array.")
    form: dict[str, str] = {"intent": str(payload.get("intent", "save"))}
    for row in sets:
        if not isinstance(row, dict):
            abort(400, description="Every set must be an object.")
        try:
            prescription_id, order = int(row["prescription_id"]), int(row["order"])
        except (KeyError, TypeError, ValueError):
            abort(400, description="Every set requires prescription_id and order.")
        form[f"row-{prescription_id}-{order}"] = "1"
        prefix = f"set-{prescription_id}-{order}"
        fields = (
            ("load_kg", "load"),
            ("reps", "reps"),
            ("rpe", "rpe"),
            ("note", "note"),
        )
        for source, target in fields:
            if row.get(source) is not None:
                form[f"{prefix}-{target}"] = str(row[source])
        if row.get("completed") is True:
            form[f"{prefix}-completed"] = "1"
        if row.get("skipped") is True:
            form[f"{prefix}-skipped"] = "1"
    result = save_training_session(training_session, athlete_id, form)
    if result.errors:
        return jsonify(envelope({"errors": list(result.errors)})), 422
    return jsonify(envelope(session_dto(athlete_id, session_id)))


@athlete_app_bp.get("/check-ins")
def check_ins():
    return jsonify(envelope(checkins_dto(_athlete_id())))


@athlete_app_bp.post("/check-ins")
def create_check_in():
    athlete_id = _athlete_id()
    athlete = db.session.get(Athlete, athlete_id)
    settings = checkin_settings(athlete_id)
    if athlete is None or settings is None:
        abort(404)
    payload = _json_object()
    form = {name: str(value) for name, value in payload.items() if value is not None}
    submission = validate_submission(form, settings)
    if not submission.is_valid:
        return jsonify(envelope({"errors": submission.errors})), 422
    item = WeeklyCheckin(
        athlete=athlete,
        week_ending=submission.values["week_ending"],
        training_included=settings.training_enabled,
        nutrition_included=settings.nutrition_enabled,
        sleep_quality=submission.values["sleep_quality"],
        stress=submission.values["stress"],
        general_notes=form.get("general_notes", "").strip() or None,
    )
    if settings.training_enabled:
        for name in ("training_adherence", "fatigue", "recovery", "motivation"):
            setattr(item, name, submission.values[name])
        item.pain_present = payload.get("pain_present") is True
        item.training_notes = form.get("training_notes", "").strip() or None
    if settings.nutrition_enabled:
        for name in (
            "average_bodyweight_kg",
            "calories_average",
            "protein_average_g",
            "carbohydrate_average_g",
            "fat_average_g",
            "fibre_average_g",
            "steps_average",
            "nutrition_adherence",
        ):
            setattr(item, name, submission.values[name])
        item.nutrition_notes = form.get("nutrition_notes", "").strip() or None
    db.session.add(item)
    db.session.commit()
    response = jsonify(envelope(checkins_dto(athlete_id)[0]))
    response.status_code = 201
    response.headers["Location"] = f"/api/athlete/v1/check-ins/{item.id}"
    return response


@athlete_app_bp.get("/nutrition/plan")
def nutrition_plan():
    assignment = current_app.extensions["meal_plan_workflow"].current_for_athlete(
        _athlete_id(), datetime.now(UTC).date()
    )
    return jsonify(envelope(meal_plan_dto(assignment) if assignment else None))


@athlete_app_bp.get("/progress")
def progress():
    data = progress_dto(_athlete_id(), today=datetime.now(UTC).date())
    if data is None:
        abort(404)
    return jsonify(envelope(data))
