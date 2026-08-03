from __future__ import annotations

from datetime import UTC, datetime

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from .extensions import db
from .models.athlete import Athlete
from .models.checkins import AthleteCheckinSettings
from .models.nutrition_checkin import NutritionCheckIn
from .services.athlete_dashboard import get_athlete_dashboard

athletes_bp = Blueprint("athletes", __name__)


@athletes_bp.get("/athlete/dashboard")
def dashboard():
    athlete_id = session.get("athlete_id")
    if isinstance(athlete_id, bool) or not isinstance(athlete_id, int):
        abort(401)

    dashboard_data = get_athlete_dashboard(
        athlete_id,
        today=datetime.now(UTC).date(),
    )
    if dashboard_data is None:
        abort(401)

    return render_template(
        "athletes/athlete_dashboard.html",
        dashboard=dashboard_data,
    )


def _optional_float(value: str | None) -> float | None:
    if not value or not value.strip():
        return None
    return float(value)


def _optional_int(value: str | None) -> int | None:
    if not value or not value.strip():
        return None
    return int(value)


def _required_score(name: str) -> int:
    value = request.form.get(name, "").strip()

    if not value:
        raise ValueError(name)

    score = int(value)

    if score < 1 or score > 10:
        raise ValueError(name)

    return score


@athletes_bp.get("/athletes")
def athlete_list():
    athletes = Athlete.query.order_by(
        Athlete.status.asc(),
        Athlete.last_name.asc(),
        Athlete.first_name.asc(),
    ).all()

    return render_template(
        "athletes/list.html",
        athletes=athletes,
    )


@athletes_bp.post("/athletes")
def create_athlete():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()

    if not first_name or not last_name or not email:
        return redirect(url_for("athletes.athlete_list"))

    athlete = Athlete(
        first_name=first_name,
        last_name=last_name,
        email=email,
        instagram=request.form.get("instagram", "").strip() or None,
        bodyweight_kg=_optional_float(request.form.get("bodyweight_kg")),
        weight_class=request.form.get("weight_class", "").strip() or None,
        federation=request.form.get("federation", "").strip() or None,
        next_competition=request.form.get("next_competition", "").strip() or None,
    )

    db.session.add(athlete)
    db.session.commit()

    return redirect(
        url_for(
            "athletes.athlete_dashboard",
            athlete_id=athlete.id,
        )
    )


@athletes_bp.get("/athletes/<int:athlete_id>")
def athlete_dashboard(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)

    if athlete is None:
        abort(404)

    checkins = NutritionCheckIn.query.filter_by(athlete_id=athlete.id).all()

    checkins.sort(
        key=lambda checkin: checkin.submitted_at,
        reverse=True,
    )

    latest_checkin = checkins[0] if checkins else None
    settings = AthleteCheckinSettings.query.filter_by(athlete_id=athlete.id).first()
    if settings is None:
        settings = AthleteCheckinSettings(
            athlete_id=athlete.id,
            training_enabled=True,
            nutrition_enabled=False,
            workflow_active=True,
            checkin_day=0,
        )

    return render_template(
        "athletes/dashboard.html",
        athlete=athlete,
        checkins=checkins,
        latest_checkin=latest_checkin,
        checkin_settings=settings,
        weekly_checkin_due=settings.is_due_on(datetime.now(UTC).date()),
    )


@athletes_bp.get("/athletes/<int:athlete_id>/nutrition-checkins/new")
def nutrition_checkin_form(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)

    if athlete is None:
        abort(404)

    return render_template(
        "athletes/nutrition_checkin.html",
        athlete=athlete,
        errors={},
        form={},
    )


@athletes_bp.post("/athletes/<int:athlete_id>/nutrition-checkins")
def create_nutrition_checkin(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)

    if athlete is None:
        abort(404)

    try:
        checkin = NutritionCheckIn(
            athlete=athlete,
            bodyweight_kg=_optional_float(request.form.get("bodyweight_kg")),
            average_calories=_optional_int(request.form.get("average_calories")),
            average_protein_g=_optional_int(request.form.get("average_protein_g")),
            average_steps=_optional_int(request.form.get("average_steps")),
            nutrition_adherence=_required_score("nutrition_adherence"),
            hunger=_required_score("hunger"),
            energy=_required_score("energy"),
            sleep_quality=_required_score("sleep_quality"),
            stress=_required_score("stress"),
            digestion=_required_score("digestion"),
            training_performance=_required_score("training_performance"),
            wins=request.form.get("wins", "").strip() or None,
            challenges=request.form.get("challenges", "").strip() or None,
            upcoming_events=request.form.get("upcoming_events", "").strip() or None,
            questions=request.form.get("questions", "").strip() or None,
        )
    except (TypeError, ValueError):
        return (
            render_template(
                "athletes/nutrition_checkin.html",
                athlete=athlete,
                errors={"scores": "Complete every score using a number from 1 to 10."},
                form=request.form,
            ),
            400,
        )

    if checkin.bodyweight_kg is not None:
        athlete.bodyweight_kg = checkin.bodyweight_kg

    db.session.add(checkin)
    db.session.commit()

    return redirect(
        url_for(
            "athletes.athlete_dashboard",
            athlete_id=athlete.id,
        )
    )


@athletes_bp.post(
    "/athletes/<int:athlete_id>/nutrition-checkins/<int:checkin_id>/review"
)
def review_nutrition_checkin(athlete_id: int, checkin_id: int):
    checkin = NutritionCheckIn.query.filter_by(
        id=checkin_id,
        athlete_id=athlete_id,
    ).first_or_404()

    checkin.coach_response = request.form.get("coach_response", "").strip() or None
    checkin.reviewed = True

    db.session.commit()

    return redirect(
        url_for(
            "athletes.athlete_dashboard",
            athlete_id=athlete_id,
        )
    )
