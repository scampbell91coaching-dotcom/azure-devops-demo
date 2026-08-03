from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy import or_

from .extensions import db
from .models.exercise_library import Exercise

exercise_library_bp = Blueprint("exercise_library", __name__)


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(value)


def _optional_float(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    return float(value)


@exercise_library_bp.get("/exercise-library")
def index():
    movement = request.args.get("movement", "").strip()
    search = request.args.get("q", "").strip()

    query = Exercise.query

    if movement:
        query = query.filter_by(movement=movement)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Exercise.name.ilike(pattern),
                Exercise.aliases.ilike(pattern),
                Exercise.family.ilike(pattern),
                Exercise.primary_muscles.ilike(pattern),
                Exercise.secondary_muscles.ilike(pattern),
                Exercise.equipment.ilike(pattern),
            )
        )

    exercises = query.order_by(
        Exercise.movement.asc(),
        Exercise.name.asc(),
    ).all()

    return render_template(
        "exercises/index.html",
        exercises=exercises,
        movement=movement,
        search=search,
    )


@exercise_library_bp.post("/exercise-library")
def create_exercise():
    name = request.form.get("name", "").strip()
    movement = request.form.get("movement", "").strip().lower()

    if not name or movement not in {
        "squat",
        "bench",
        "deadlift",
        "accessory",
        "warmup",
    }:
        abort(400)

    if Exercise.query.filter_by(name=name).first() is not None:
        abort(409)

    exercise = Exercise(
        name=name,
        movement=movement,
        category=request.form.get("category", "").strip() or "main",
        variation=request.form.get("variation", "").strip() or None,
        equipment=request.form.get("equipment", "").strip() or None,
        primary_muscles=request.form.get("primary_muscles", "").strip() or None,
        secondary_muscles=request.form.get("secondary_muscles", "").strip() or None,
        fatigue_rating=_optional_int(request.form.get("fatigue_rating")) or 3,
        default_sets=_optional_int(request.form.get("default_sets")),
        default_reps=request.form.get("default_reps", "").strip() or None,
        default_rpe=_optional_float(request.form.get("default_rpe")),
        default_rest_seconds=_optional_int(request.form.get("default_rest_seconds")),
        coaching_cues=request.form.get("coaching_cues", "").strip() or None,
        video_url=request.form.get("video_url", "").strip() or None,
    )

    db.session.add(exercise)
    db.session.commit()

    return redirect(url_for("exercise_library.index"))


@exercise_library_bp.get("/exercise-library/<int:exercise_id>/edit")
def edit(exercise_id: int):
    exercise = db.session.get(Exercise, exercise_id)

    if exercise is None:
        abort(404)

    return render_template(
        "exercises/edit.html",
        exercise=exercise,
    )


@exercise_library_bp.post("/exercise-library/<int:exercise_id>/edit")
def update(exercise_id: int):
    exercise = db.session.get(Exercise, exercise_id)

    if exercise is None:
        abort(404)

    exercise.name = request.form.get("name", "").strip() or exercise.name
    exercise.movement = (
        request.form.get("movement", "").strip().lower() or exercise.movement
    )
    exercise.category = request.form.get("category", "").strip() or exercise.category
    exercise.variation = request.form.get("variation", "").strip() or None
    exercise.equipment = request.form.get("equipment", "").strip() or None
    exercise.primary_muscles = request.form.get("primary_muscles", "").strip() or None
    exercise.secondary_muscles = (
        request.form.get("secondary_muscles", "").strip() or None
    )
    exercise.fatigue_rating = (
        _optional_int(request.form.get("fatigue_rating")) or exercise.fatigue_rating
    )
    exercise.default_sets = _optional_int(request.form.get("default_sets"))
    exercise.default_reps = request.form.get("default_reps", "").strip() or None
    exercise.default_rpe = _optional_float(request.form.get("default_rpe"))
    exercise.default_rest_seconds = _optional_int(
        request.form.get("default_rest_seconds")
    )
    exercise.coaching_cues = request.form.get("coaching_cues", "").strip() or None
    exercise.video_url = request.form.get("video_url", "").strip() or None

    db.session.commit()

    return redirect(url_for("exercise_library.index"))
