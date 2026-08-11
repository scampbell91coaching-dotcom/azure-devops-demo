from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from flask import Blueprint, abort, flash, redirect, request, url_for

from .auth import roles_required
from .extensions import db
from .models.athlete import Athlete
from .models.athlete_state import CoachTechnicalObservation
from .models.external_coaching_review import ExternalCoachingReview
from .models.programming import TrainingSessionLog, TrainingSetResult
from .models.user import UserRole

external_reviews_bp = Blueprint("external_reviews", __name__)


def _optional_id(name: str) -> int | None:
    value = request.form.get(name, "").strip()
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        abort(400, description=f"Invalid {name.replace('_', ' ')}.")
    if parsed <= 0:
        abort(400, description=f"Invalid {name.replace('_', ' ')}.")
    return parsed


def _external_url() -> str | None:
    value = request.form.get("external_url", "").strip()
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or len(value) > 2048:
        abort(400, description="External URL must be a valid HTTP or HTTPS URL.")
    return value


@external_reviews_bp.post("/athletes/<int:athlete_id>/external-reviews")
@roles_required(UserRole.COACH)
def create(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(404)

    summary = request.form.get("coach_summary", "").strip()
    action = request.form.get("action", "").strip()
    reviewed_at_value = request.form.get("reviewed_at", "").strip()
    if not summary or not action or not reviewed_at_value:
        abort(400, description="Reviewed at, coach summary and action are required.")
    try:
        reviewed_at = datetime.fromisoformat(reviewed_at_value)
    except ValueError:
        abort(400, description="Choose a valid review date and time.")

    session_log_id = _optional_id("session_log_id")
    set_result_id = _optional_id("set_result_id")
    observation_id = _optional_id("observation_id")
    session_log = db.session.get(TrainingSessionLog, session_log_id) if session_log_id else None
    set_result = db.session.get(TrainingSetResult, set_result_id) if set_result_id else None
    observation = db.session.get(CoachTechnicalObservation, observation_id) if observation_id else None

    if session_log_id and (session_log is None or session_log.athlete_id != athlete.id):
        abort(404)
    if set_result_id and (
        set_result is None or set_result.session_log.athlete_id != athlete.id
    ):
        abort(404)
    if set_result is not None and session_log is not None and set_result.session_log_id != session_log.id:
        abort(400, description="The selected set does not belong to the selected session.")
    if observation_id and (observation is None or observation.athlete_id != athlete.id):
        abort(404)

    db.session.add(
        ExternalCoachingReview(
            athlete=athlete,
            channel="whatsapp",
            reviewed_at=reviewed_at,
            session_log=session_log,
            set_result=set_result,
            observation=observation,
            coach_summary=summary,
            action=action,
            follow_up_required="follow_up_required" in request.form,
            resolved="resolved" in request.form,
            external_url=_external_url(),
        )
    )
    db.session.commit()
    flash("External coaching review recorded.", "success")
    return redirect(url_for("athletes.athlete_dashboard", athlete_id=athlete.id) + "#external-reviews")


@external_reviews_bp.post("/athletes/<int:athlete_id>/external-reviews/<int:review_id>/resolve")
@roles_required(UserRole.COACH)
def resolve(athlete_id: int, review_id: int):
    review = db.session.get(ExternalCoachingReview, review_id)
    if review is None or review.athlete_id != athlete_id:
        abort(404)
    review.resolved = True
    db.session.commit()
    flash("External review marked resolved.", "success")
    return redirect(url_for("athletes.athlete_dashboard", athlete_id=athlete_id) + "#external-reviews")
