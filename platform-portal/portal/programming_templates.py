from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from flask import Blueprint, abort, redirect, render_template, request, url_for

from .extensions import db
from .models.athlete import Athlete
from .models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from .programming_services.revisions import append_revision

programming_templates_bp = Blueprint("programming_templates", __name__)

DAY_TEMPLATES = {
    "S": {
        "label": "Squat",
        "description": "Squat-focused session.",
        "exercises": [("Competition Squat", 1, "3", 7)],
    },
    "B": {
        "label": "Bench",
        "description": "Bench-focused session.",
        "exercises": [("Competition Bench Press", 1, "5", 7)],
    },
    "D": {
        "label": "Deadlift",
        "description": "Deadlift-focused session.",
        "exercises": [("Competition Deadlift", 1, "3", 7)],
    },
    "SB": {
        "label": "Squat + Bench",
        "description": "Primary squat and bench session.",
        "exercises": [
            ("Competition Squat", 1, "3", 7),
            ("Competition Bench Press", 1, "4", 7),
        ],
    },
    "BD": {
        "label": "Bench + Deadlift",
        "description": "Primary bench and deadlift session.",
        "exercises": [
            ("Competition Bench Press", 1, "4", 7),
            ("Competition Deadlift", 1, "3", 7),
        ],
    },
    "SBD": {
        "label": "Squat + Bench + Deadlift",
        "description": "Full competition lift session.",
        "exercises": [
            ("Competition Squat", 1, "3", 7),
            ("Competition Bench Press", 1, "4", 7),
            ("Competition Deadlift", 1, "3", 7),
        ],
    },
}


@dataclass(frozen=True)
class FactoryRequest:
    squat_days: int
    bench_days: int
    deadlift_days: int
    weeks: int


def day_templates() -> dict[str, dict[str, object]]:
    return deepcopy(DAY_TEMPLATES)


def _bounded_int(name: str, minimum: int, maximum: int) -> int:
    value = request.form.get(name, type=int)
    if value is None or value < minimum or value > maximum:
        abort(400)
    return value


def _build_day_keys(factory: FactoryRequest) -> list[str]:
    remaining = {
        "S": factory.squat_days,
        "B": factory.bench_days,
        "D": factory.deadlift_days,
    }
    result: list[str] = []

    while remaining["S"] and remaining["B"] and remaining["D"]:
        result.append("SBD")
        remaining["S"] -= 1
        remaining["B"] -= 1
        remaining["D"] -= 1

    while remaining["S"] and remaining["B"]:
        result.append("SB")
        remaining["S"] -= 1
        remaining["B"] -= 1

    while remaining["B"] and remaining["D"]:
        result.append("BD")
        remaining["B"] -= 1
        remaining["D"] -= 1

    result.extend(["S"] * remaining["S"])
    result.extend(["B"] * remaining["B"])
    result.extend(["D"] * remaining["D"])
    return result


def _apply_template(session: TrainingSession, template_key: str) -> None:
    template = DAY_TEMPLATES[template_key]
    for position, values in enumerate(template["exercises"], start=1):
        name, sets, reps, rpe = values
        db.session.add(
            ExercisePrescription(
                session=session,
                position=position,
                exercise_name=name,
                sets=sets,
                reps=reps,
                rpe=rpe,
            )
        )


@programming_templates_bp.get("/programming/block-factory")
def block_factory():
    athletes = Athlete.query.order_by(
        Athlete.last_name.asc(), Athlete.first_name.asc()
    ).all()
    return render_template("programming/block_factory.html", athletes=athletes)


@programming_templates_bp.post("/programming/block-factory")
def create_factory_block():
    athlete = db.session.get(Athlete, request.form.get("athlete_id", type=int))
    if athlete is None:
        abort(404)

    factory = FactoryRequest(
        squat_days=_bounded_int("squat_days", 1, 5),
        bench_days=_bounded_int("bench_days", 1, 5),
        deadlift_days=_bounded_int("deadlift_days", 1, 3),
        weeks=_bounded_int("weeks", 1, 12),
    )

    name = request.form.get("name", "").strip()
    if not name:
        abort(400)

    block = TrainingBlock(
        athlete=athlete,
        name=name,
        objective=request.form.get("objective", "").strip() or None,
        status="draft",
    )
    db.session.add(block)
    db.session.flush()

    day_keys = _build_day_keys(factory)
    for week_number in range(1, factory.weeks + 1):
        week = TrainingWeek(
            block=block, name=f"Week {week_number}", position=week_number
        )
        db.session.add(week)
        db.session.flush()
        for day_number, key in enumerate(day_keys, start=1):
            session = TrainingSession(
                week=week,
                name=str(DAY_TEMPLATES[key]["label"]),
                day_label=f"Day {day_number}",
                position=day_number,
            )
            db.session.add(session)
            db.session.flush()
            _apply_template(session, key)

    append_revision(block, change_type="template_programme_created", summary="Created programme from block template")
    db.session.commit()
    return redirect(url_for("programming.block", block_id=block.id))


@programming_templates_bp.post(
    "/programming/sessions/<int:session_id>/apply-day-template"
)
def apply_day_template(session_id: int):
    session = db.session.get(TrainingSession, session_id)
    if session is None:
        abort(404)
    key = request.form.get("template_key", "").strip().upper()
    if key not in DAY_TEMPLATES:
        abort(400)
    if request.form.get("replace_existing") == "1":
        for item in list(session.prescriptions):
            db.session.delete(item)
        db.session.flush()
    start = len(session.prescriptions) + 1
    for offset, values in enumerate(DAY_TEMPLATES[key]["exercises"]):
        name, sets, reps, rpe = values
        db.session.add(
            ExercisePrescription(
                session=session,
                position=start + offset,
                exercise_name=name,
                sets=sets,
                reps=reps,
                rpe=rpe,
            )
        )
    append_revision(session.week.block, change_type="day_template_applied", summary=f"Applied day template {key}")
    db.session.commit()
    return redirect(url_for("programming.session", session_id=session.id))
