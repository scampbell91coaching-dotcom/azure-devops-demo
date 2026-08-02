from __future__ import annotations

from flask import Blueprint, abort, jsonify

from .extensions import db
from .models.exercise_library import DayTemplate, Exercise
from .models.programming import ExercisePrescription, TrainingBlock

programming_engine_bp = Blueprint("programming_engine", __name__)


@programming_engine_bp.get("/programming/api/exercise-library")
def exercise_library_api():
    rows = (
        Exercise.query.filter_by(active=True)
        .order_by(
            Exercise.movement.asc(),
            Exercise.name.asc(),
        )
        .all()
    )

    return jsonify(
        [
            {
                "id": item.id,
                "name": item.name,
                "movement": item.movement,
                "category": item.category,
                "variation": item.variation,
                "fatigue_rating": item.fatigue_rating,
                "default_sets": item.default_sets,
                "default_reps": item.default_reps,
                "default_rpe": item.default_rpe,
                "default_rest_seconds": item.default_rest_seconds,
            }
            for item in rows
        ]
    )


@programming_engine_bp.get("/programming/api/day-templates")
def day_templates_api():
    templates = (
        DayTemplate.query.filter_by(active=True).order_by(DayTemplate.code.asc()).all()
    )

    return jsonify(
        [
            {
                "id": template.id,
                "code": template.code,
                "name": template.name,
                "description": template.description,
                "exercises": [
                    {
                        "exercise_id": item.exercise.id,
                        "exercise_name": item.exercise.name,
                        "position": item.position,
                        "sets": item.sets,
                        "reps": item.reps,
                        "rpe": item.rpe,
                        "percentage": item.percentage,
                        "notes": item.notes,
                    }
                    for item in template.exercises
                ],
            }
            for template in templates
        ]
    )


@programming_engine_bp.get("/programming/api/blocks/<int:block_id>/metrics")
def block_metrics(block_id: int):
    block = db.session.get(TrainingBlock, block_id)

    if block is None:
        abort(404)

    prescriptions: list[ExercisePrescription] = []

    for week in block.weeks:
        for session in week.sessions:
            prescriptions.extend(session.prescriptions)

    total_sets = sum(item.sets or 0 for item in prescriptions)
    total_reps = sum(
        (item.sets or 0) * _reps_as_number(item.reps) for item in prescriptions
    )
    tonnage = sum(
        (item.sets or 0) * _reps_as_number(item.reps) * (item.load_kg or 0)
        for item in prescriptions
    )

    rpes = [item.rpe for item in prescriptions if item.rpe is not None]
    loads = [item.load_kg for item in prescriptions if item.load_kg is not None]

    return jsonify(
        {
            "block_id": block.id,
            "exercise_count": len(prescriptions),
            "total_sets": total_sets,
            "total_reps": total_reps,
            "tonnage_kg": round(tonnage, 2),
            "average_rpe": (round(sum(rpes) / len(rpes), 2) if rpes else None),
            "average_load_kg": (round(sum(loads) / len(loads), 2) if loads else None),
        }
    )


def _reps_as_number(value: str | None) -> int:
    if not value:
        return 0

    try:
        return int(value)
    except ValueError:
        first = value.split(",")[0].strip()
        return int(first) if first.isdigit() else 0
