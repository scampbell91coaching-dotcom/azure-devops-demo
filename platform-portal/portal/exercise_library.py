from __future__ import annotations

import re

from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy import and_, func, or_

from .extensions import db
from .models.exercise_library import Exercise
from .services.exercise_knowledge_import import find_exercise_by_identity

exercise_library_bp = Blueprint("exercise_library", __name__)


SEARCHABLE_FIELDS = (
    Exercise.name,
    Exercise.aliases,
    Exercise.family,
    Exercise.category,
    Exercise.primary_muscles,
    Exercise.secondary_muscles,
    Exercise.equipment,
    Exercise.goal,
)


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
    category = request.args.get("category", "").strip()
    search = request.args.get("q", "").strip()
    page = max(1, request.args.get("page", 1, type=int))

    query = Exercise.query.filter_by(active=True)

    if movement:
        query = query.filter_by(movement=movement)
    if category:
        query = query.filter_by(category=category)

    if search:
        terms = re.findall(r"[a-z0-9]+", search.casefold())
        if terms:
            query = query.filter(
                and_(
                    *(
                        or_(
                            *(
                                func.replace(
                                    func.replace(func.lower(field), "-", " "),
                                    "'",
                                    "",
                                ).like(f"%{term}%")
                                for field in SEARCHABLE_FIELDS
                            )
                        )
                        for term in terms
                    )
                )
            )

    pagination = query.order_by(
        Exercise.movement.asc(),
        Exercise.name.asc(),
    ).paginate(page=page, per_page=24, error_out=False)

    movements = [value for value, in db.session.query(Exercise.movement).filter_by(active=True).distinct().order_by(Exercise.movement)]
    categories = [value for value, in db.session.query(Exercise.category).filter_by(active=True).distinct().order_by(Exercise.category)]

    return render_template(
        "exercises/index.html",
        exercises=pagination.items,
        pagination=pagination,
        movement=movement,
        category=category,
        search=search,
        movements=movements,
        categories=categories,
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

    if find_exercise_by_identity(name) is not None:
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

    requested_name = request.form.get("name", "").strip() or exercise.name
    identity_match = find_exercise_by_identity(requested_name)
    if identity_match is not None and identity_match.id != exercise.id:
        abort(409)
    exercise.name = requested_name
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
    # A coach edit transfers ownership of the complete row. Future catalogue
    # imports still use its name and aliases for duplicate detection, but do
    # not replace any coach-maintained values.
    exercise.catalogue_version = None

    db.session.commit()

    return redirect(url_for("exercise_library.index"))
