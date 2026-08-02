from __future__ import annotations

from datetime import UTC, date, datetime

from flask import Blueprint, abort, redirect, render_template, request, url_for

from .extensions import db
from .models.athlete import Athlete
from .models.checkins import AthleteCheckinSettings, WeeklyCheckin

checkins_bp = Blueprint("checkins", __name__)


def _settings_for(athlete: Athlete) -> AthleteCheckinSettings:
    settings = AthleteCheckinSettings.query.filter_by(athlete_id=athlete.id).first()

    if settings is None:
        settings = AthleteCheckinSettings(athlete=athlete)
        db.session.add(settings)
        db.session.commit()

    return settings


def _optional_int(name: str) -> int | None:
    value = request.form.get(name, "").strip()
    return int(value) if value else None


def _optional_float(name: str) -> float | None:
    value = request.form.get(name, "").strip()
    return float(value) if value else None


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
    settings.checkin_day = request.form.get("checkin_day", type=int) or 0

    db.session.commit()
    return redirect(url_for("checkins.settings", athlete_id=athlete.id))


@checkins_bp.get("/athletes/<int:athlete_id>/check-ins/new")
def new(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(404)

    settings = _settings_for(athlete)

    return render_template(
        "checkins/form.html",
        athlete=athlete,
        settings=settings,
        today=datetime.now(UTC).date().isoformat(),
    )


@checkins_bp.post("/athletes/<int:athlete_id>/check-ins")
def create(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(404)

    settings = _settings_for(athlete)

    item = WeeklyCheckin(
        athlete=athlete,
        week_ending=date.fromisoformat(request.form["week_ending"]),
        training_included=settings.training_enabled,
        nutrition_included=settings.nutrition_enabled,
        sleep_quality=_optional_int("sleep_quality"),
        stress=_optional_int("stress"),
        general_notes=request.form.get("general_notes", "").strip() or None,
    )

    if settings.training_enabled:
        item.training_adherence = _optional_int("training_adherence")
        item.fatigue = _optional_int("fatigue")
        item.recovery = _optional_int("recovery")
        item.motivation = _optional_int("motivation")
        item.pain_present = request.form.get("pain_present") == "1"
        item.training_notes = request.form.get("training_notes", "").strip() or None

    if settings.nutrition_enabled:
        item.average_bodyweight_kg = _optional_float("average_bodyweight_kg")
        item.calories_average = _optional_int("calories_average")
        item.protein_average_g = _optional_int("protein_average_g")
        item.steps_average = _optional_int("steps_average")
        item.nutrition_adherence = _optional_int("nutrition_adherence")
        item.nutrition_notes = request.form.get("nutrition_notes", "").strip() or None

    db.session.add(item)
    db.session.commit()
    return redirect(url_for("checkins.detail", checkin_id=item.id))


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

    item.coach_notes = request.form.get("coach_notes", "").strip() or None
    item.status = "reviewed"
    item.coach_reviewed_at = datetime.now(UTC)

    db.session.commit()
    return redirect(url_for("checkins.detail", checkin_id=item.id))
