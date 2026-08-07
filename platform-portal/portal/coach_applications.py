from __future__ import annotations

from flask import Blueprint, abort, g, redirect, render_template, request, url_for

from .auth import roles_required
from .extensions import db
from .models.coaching_application import CoachingApplication
from .models.user import UserRole

coach_applications_bp = Blueprint("coach_applications", __name__)

APPLICATION_STATUSES = ("new", "reviewing", "contacted", "accepted", "declined")
PENDING_APPLICATION_STATUSES = ("new", "reviewing")


@coach_applications_bp.app_context_processor
def application_navigation_count() -> dict[str, int]:
    user = g.get("current_user")
    if user is None or user.user_role != UserRole.COACH:
        return {"pending_application_count": 0}
    count = CoachingApplication.query.filter(
        CoachingApplication.status.in_(PENDING_APPLICATION_STATUSES)
    ).count()
    return {"pending_application_count": count}


@coach_applications_bp.get("/applications")
@roles_required(UserRole.COACH)
def index():
    applications = CoachingApplication.query.order_by(
        CoachingApplication.submitted_at.desc(),
        CoachingApplication.id.desc(),
    ).all()
    return render_template(
        "coach/applications/index.html",
        applications=applications,
    )


@coach_applications_bp.get("/applications/<int:application_id>")
@roles_required(UserRole.COACH)
def detail(application_id: int):
    application = db.session.get(CoachingApplication, application_id)
    if application is None:
        abort(404)
    return render_template(
        "coach/applications/detail.html",
        application=application,
        application_statuses=APPLICATION_STATUSES,
    )


@coach_applications_bp.post("/applications/<int:application_id>/status")
@roles_required(UserRole.COACH)
def update_status(application_id: int):
    application = db.session.get(CoachingApplication, application_id)
    if application is None:
        abort(404)
    status = request.form.get("status", "")
    if status not in APPLICATION_STATUSES:
        abort(400, description="Choose a valid application status.")
    application.status = status
    db.session.commit()
    return redirect(url_for("coach_applications.detail", application_id=application.id))
