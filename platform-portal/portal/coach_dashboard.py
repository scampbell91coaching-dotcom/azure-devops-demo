from flask import Blueprint, render_template

from .services.coach_dashboard import CoachDashboardService

coach_dashboard_bp = Blueprint("coach_dashboard", __name__)


@coach_dashboard_bp.get("/coach")
def index():
    return render_template(
        "coach/dashboard.html",
        dashboard=CoachDashboardService().build(),
    )
