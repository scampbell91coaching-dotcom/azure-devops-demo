from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

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
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models.athlete import Athlete
from .models.checkins import AthleteCheckinSettings
from .models.nutrition_checkin import NutritionCheckIn
from .models.programming import TrainingBlock, TrainingSession
from .services.athlete_dashboard import get_athlete_dashboard
from .services.nutrition_dashboard import get_nutrition_dashboard
from .nutrition_imports import _summary

athletes_bp = Blueprint("athletes", __name__)


@athletes_bp.get("/nutrition")
def nutrition_dashboard():
    return render_template(
        "nutrition/index.html",
        dashboard=get_nutrition_dashboard(),
    )


@athletes_bp.get("/athlete/dashboard")
def dashboard():
    user = g.get("current_user")
    athlete_id = user.athlete_id if user is not None else session.get("athlete_id")
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


def _signed_in_athlete_id() -> int:
    user = g.get("current_user")
    athlete_id = user.athlete_id if user is not None else session.get("athlete_id")
    if isinstance(athlete_id, bool) or not isinstance(athlete_id, int):
        abort(401)
    return athlete_id


@athletes_bp.get("/athlete/programme")
def programme():
    athlete_id = _signed_in_athlete_id()
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        abort(401)
    block = (
        TrainingBlock.query.filter_by(athlete_id=athlete_id, status="active")
        .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
        .first()
    )
    return render_template("athletes/programme.html", athlete=athlete, block=block)


@athletes_bp.get("/athlete/programme/sessions/<int:session_id>")
def programme_session(session_id: int):
    athlete_id = _signed_in_athlete_id()
    training_session = db.session.get(TrainingSession, session_id)
    if training_session is None or training_session.week.block.athlete_id != athlete_id:
        abort(404)
    if training_session.week.block.status != "active":
        abort(404)
    return render_template(
        "athletes/programme_session.html",
        session=training_session,
        week=training_session.week,
        block=training_session.week.block,
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


def _parse_date(name: str, errors: dict[str, str]) -> date | None:
    value = request.form.get(name, "").strip()
    # Compatibility for established API/form clients; the browser form always
    # supplies an explicit required date.
    if not value:
        return datetime.now(UTC).date()
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors[name] = "Enter a valid check-in date."
        return None
    if parsed > datetime.now(UTC).date():
        errors[name] = "Check-in date cannot be in the future."
    return parsed


def _number(name: str, label: str, minimum: float, maximum: float, errors: dict[str, str], *, integer: bool = False):
    value = request.form.get(name, "").strip()
    if not value:
        return None
    try:
        result = int(value) if integer else float(value)
    except ValueError:
        errors[name] = f"{label} must be a number."
        return None
    if result < minimum or result > maximum:
        errors[name] = f"{label} must be between {minimum:g} and {maximum:g}."
    return result


def _nutrition_form_values() -> tuple[dict, dict[str, str]]:
    errors: dict[str, str] = {}
    values = {
        "checkin_date": _parse_date("checkin_date", errors),
        "bodyweight_kg": _number("bodyweight_kg", "Average bodyweight", 25, 350, errors),
        "calorie_target": _number("calorie_target", "Calorie target", 500, 10000, errors, integer=True),
        "average_calories": _number("average_calories", "Average calorie intake", 0, 10000, errors, integer=True),
        "protein_target_g": _number("protein_target_g", "Protein target", 0, 500, errors, integer=True),
        "average_protein_g": _number("average_protein_g", "Average protein", 0, 500, errors, integer=True),
        "carbohydrate_target_g": _number("carbohydrate_target_g", "Carbohydrate target", 0, 1000, errors, integer=True),
        "average_carbohydrate_g": _number("average_carbohydrate_g", "Average carbohydrate", 0, 1000, errors, integer=True),
        "fat_target_g": _number("fat_target_g", "Fat target", 0, 400, errors, integer=True),
        "average_fat_g": _number("average_fat_g", "Average fat", 0, 400, errors, integer=True),
        "average_fibre_g": _number("average_fibre_g", "Average fibre", 0, 150, errors),
        "average_fluid_l": _number("average_fluid_l", "Average fluid", 0, 15, errors),
        "average_steps": _number("average_steps", "Average steps", 0, 100000, errors, integer=True),
        "average_sleep_hours": _number("average_sleep_hours", "Average sleep", 0, 24, errors),
    }
    for name in ("nutrition_adherence", "hunger", "energy", "sleep_quality", "digestion"):
        try:
            values[name] = _required_score(name)
        except (TypeError, ValueError):
            errors[name] = "Choose a score from 1 to 10."
    return values, errors


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
        errors={},
        form={},
    )


@athletes_bp.post("/athletes")
def create_athlete():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()

    form = request.form
    if not first_name or not last_name or not email:
        athletes = Athlete.query.order_by(
            Athlete.status.asc(), Athlete.last_name.asc(), Athlete.first_name.asc()
        ).all()
        return render_template(
            "athletes/list.html", athletes=athletes,
            errors={"form": "First name, last name and email are required."}, form=form,
        ), 400

    if Athlete.query.filter(db.func.lower(Athlete.email) == email).first() is not None:
        athletes = Athlete.query.order_by(
            Athlete.status.asc(), Athlete.last_name.asc(), Athlete.first_name.asc()
        ).all()
        return render_template(
            "athletes/list.html", athletes=athletes,
            errors={"email": "An athlete with this email already exists."}, form=form,
        ), 400

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
    try:
        db.session.commit()
    except IntegrityError:
        # The unique constraint closes the race after the friendly pre-check.
        db.session.rollback()
        athletes = Athlete.query.order_by(
            Athlete.status.asc(), Athlete.last_name.asc(), Athlete.first_name.asc()
        ).all()
        return render_template(
            "athletes/list.html", athletes=athletes,
            errors={"email": "An athlete with this email already exists."}, form=form,
        ), 400

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

    checkins.sort(key=lambda checkin: (checkin.checkin_date, checkin.id), reverse=True)
    for index, checkin in enumerate(checkins):
        older = checkins[index + 1] if index + 1 < len(checkins) else None
        checkin.weekly_bodyweight_change_kg = (
            round(checkin.bodyweight_kg - older.bodyweight_kg, 2)
            if older is not None
            and checkin.bodyweight_kg is not None
            and older.bodyweight_kg is not None
            else None
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
        imported_nutrition=_summary(athlete.id, datetime.now(UTC).date() - timedelta(days=6), datetime.now(UTC).date()),
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
        form={"checkin_date": datetime.now(UTC).date().isoformat()},
        today=datetime.now(UTC).date().isoformat(),
    )


@athletes_bp.post("/athletes/<int:athlete_id>/nutrition-checkins")
def create_nutrition_checkin(athlete_id: int):
    athlete = db.session.get(Athlete, athlete_id)

    if athlete is None:
        abort(404)

    values, errors = _nutrition_form_values()
    if errors:
        return (
            render_template(
                "athletes/nutrition_checkin.html",
                athlete=athlete,
                errors=errors,
                form=request.form,
                today=datetime.now(UTC).date().isoformat(),
            ),
            400,
        )
    checkin = NutritionCheckIn(
        athlete=athlete,
        **values,
        stress=5,
        training_performance=values["energy"],
        wins=request.form.get("wins", "").strip() or None,
        challenges=request.form.get("challenges", "").strip() or None,
        questions=request.form.get("questions", "").strip() or None,
    )

    if checkin.bodyweight_kg is not None:
        athlete.bodyweight_kg = checkin.bodyweight_kg

    db.session.add(checkin)
    db.session.commit()

    if g.get("current_user") is not None and g.current_user.role == "athlete":
        return redirect(url_for("athletes.dashboard"))
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

    response = request.form.get("coach_response", "").strip()
    if len(response) > 5000:
        abort(400, description="Coach response must be 5,000 characters or fewer.")
    checkin.coach_response = response or None
    checkin.reviewed = request.form.get("review_status", "reviewed") == "reviewed"
    checkin.reviewed_at = datetime.now(UTC) if checkin.reviewed else None

    db.session.commit()

    return redirect(
        url_for(
            "athletes.athlete_dashboard",
            athlete_id=athlete_id,
        )
    )
