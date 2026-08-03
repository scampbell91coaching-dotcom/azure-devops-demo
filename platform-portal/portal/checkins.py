from __future__ import annotations

from datetime import UTC, datetime

from flask import (
    Blueprint,
    abort,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from .extensions import db
from .models.athlete import Athlete
from .models.checkins import AthleteCheckinSettings, WeeklyCheckin
from .services.checkins import athlete_checkins, due_message, validate_submission

checkins_bp = Blueprint("checkins", __name__)


def _settings_for(athlete: Athlete) -> AthleteCheckinSettings:
    settings = AthleteCheckinSettings.query.filter_by(athlete_id=athlete.id).first()

    if settings is None:
        settings = AthleteCheckinSettings(
            athlete=athlete,
            training_enabled=True,
            nutrition_enabled=False,
            workflow_active=True,
            checkin_day=0,
        )
        db.session.add(settings)
        db.session.commit()

    return settings


def _session_athlete() -> Athlete:
    user = g.get("current_user")
    athlete_id = user.athlete_id if user is not None else session.get("athlete_id")
    if isinstance(athlete_id, bool) or not isinstance(athlete_id, int):
        abort(401)
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(401)
    return athlete


@checkins_bp.get("/check-ins")
def index():
    items = WeeklyCheckin.query.order_by(WeeklyCheckin.submitted_at.desc()).all()
    return render_template("checkins/index.html", checkins=items)


@checkins_bp.get("/athletes/<int:athlete_id>/check-in-settings")
def settings(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(404)
    return render_template(
        "checkins/settings.html",
        athlete=athlete,
        settings=_settings_for(athlete),
    )


@checkins_bp.post("/athletes/<int:athlete_id>/check-in-settings")
def update_settings(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(404)

    settings = _settings_for(athlete)
    settings.training_enabled = request.form.get("training_enabled") == "1"
    settings.nutrition_enabled = request.form.get("nutrition_enabled") == "1"
    settings.workflow_active = request.form.get("workflow_active") == "1"
    checkin_day = request.form.get("checkin_day", type=int)
    settings.checkin_day = checkin_day if checkin_day in range(7) else 0

    db.session.commit()
    return redirect(url_for("checkins.settings", athlete_id=athlete.id))


@checkins_bp.get("/athletes/<int:athlete_id>/check-ins/new")
def new(athlete_id: int):
    athlete = _session_athlete()
    if athlete.id != athlete_id:
        abort(403)

    settings = _settings_for(athlete)

    return render_template(
        "checkins/form.html",
        athlete=athlete,
        settings=settings,
        today=datetime.now(UTC).date().isoformat(),
        errors={},
        form={},
        due_message=due_message(settings, datetime.now(UTC).date()),
    )


@checkins_bp.post("/athletes/<int:athlete_id>/check-ins")
def create(athlete_id: int):
    athlete = _session_athlete()
    if athlete.id != athlete_id:
        abort(403)

    settings = _settings_for(athlete)
    submission = validate_submission(request.form, settings)
    if not submission.is_valid:
        return (
            render_template(
                "checkins/form.html",
                athlete=athlete,
                settings=settings,
                today=request.form.get("week_ending", ""),
                errors=submission.errors,
                form=request.form,
                due_message=due_message(settings, datetime.now(UTC).date()),
            ),
            400,
        )

    item = WeeklyCheckin(
        athlete=athlete,
        week_ending=submission.values["week_ending"],
        training_included=settings.training_enabled,
        nutrition_included=settings.nutrition_enabled,
        sleep_quality=submission.values["sleep_quality"],
        stress=submission.values["stress"],
        general_notes=request.form.get("general_notes", "").strip() or None,
    )

    if settings.training_enabled:
        item.training_adherence = submission.values["training_adherence"]
        item.fatigue = submission.values["fatigue"]
        item.recovery = submission.values["recovery"]
        item.motivation = submission.values["motivation"]
        item.pain_present = request.form.get("pain_present") == "1"
        item.training_notes = request.form.get("training_notes", "").strip() or None

    if settings.nutrition_enabled:
        item.average_bodyweight_kg = submission.values["average_bodyweight_kg"]
        item.calories_average = submission.values["calories_average"]
        item.protein_average_g = submission.values["protein_average_g"]
        item.steps_average = submission.values["steps_average"]
        item.nutrition_adherence = submission.values["nutrition_adherence"]
        item.nutrition_notes = request.form.get("nutrition_notes", "").strip() or None

    db.session.add(item)
    db.session.commit()
    return redirect(url_for("checkins.athlete_detail", checkin_id=item.id))


@checkins_bp.get("/athlete/check-ins")
def athlete_history():
    athlete = _session_athlete()
    settings = _settings_for(athlete)
    return render_template(
        "checkins/history.html",
        athlete=athlete,
        checkins=athlete_checkins(athlete.id),
        due_message=due_message(settings, datetime.now(UTC).date()),
    )


@checkins_bp.get("/athlete/check-ins/<int:checkin_id>")
def athlete_detail(checkin_id: int):
    athlete = _session_athlete()
    item = WeeklyCheckin.query.filter_by(
        id=checkin_id,
        athlete_id=athlete.id,
    ).first()
    if item is None:
        abort(404)
    return render_template("checkins/receipt.html", checkin=item)


@checkins_bp.get("/check-ins/<int:checkin_id>")
def detail(checkin_id: int):
    item = db.session.get(WeeklyCheckin, checkin_id)
    if item is None:
        abort(404)
    return render_template("checkins/detail.html", checkin=item)


@checkins_bp.post("/check-ins/<int:checkin_id>/review")
def review(checkin_id: int):
    item = db.session.get(WeeklyCheckin, checkin_id)
    if item is None:
        abort(404)

    coach_notes = request.form.get("coach_notes", "").strip()
    if not coach_notes:
        return render_template(
            "checkins/detail.html",
            checkin=item,
            errors={"coach_notes": "Add a response before marking this reviewed."},
        ), 400
    item.coach_notes = coach_notes
    item.status = "reviewed"
    item.coach_reviewed_at = datetime.now(UTC)

    db.session.commit()
    return redirect(url_for("checkins.detail", checkin_id=item.id))
