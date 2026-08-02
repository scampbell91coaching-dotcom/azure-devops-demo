from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from .extensions import db
from .models.athlete import Athlete
from .models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)

block_factory_bp = Blueprint("block_factory", __name__)


def _asset_path() -> Path:
    app_root = Path(current_app.root_path).parent
    return app_root / "data" / "traditional_strength_intelligence.json"


def _load_assets() -> dict[str, Any]:
    path = _asset_path()

    if not path.exists():
        return {
            "schema_version": 1,
            "exercises": [],
            "templates": {},
            "pairings": {},
            "periodisation": {},
        }

    data = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        return {}

    return data


def _fallback_templates() -> dict[str, list[dict[str, Any]]]:
    return {
        "S": [{"signature": "Competition Squat", "exercises": ["Competition Squat"]}],
        "B": [
            {
                "signature": "Competition Bench Press",
                "exercises": ["Competition Bench Press"],
            }
        ],
        "D": [
            {"signature": "Competition Deadlift", "exercises": ["Competition Deadlift"]}
        ],
        "SB": [
            {
                "signature": "Competition Squat > Competition Bench Press",
                "exercises": ["Competition Squat", "Competition Bench Press"],
            }
        ],
        "BD": [
            {
                "signature": "Competition Bench Press > Competition Deadlift",
                "exercises": ["Competition Bench Press", "Competition Deadlift"],
            }
        ],
        "SBD": [
            {
                "signature": "Competition Squat > Competition Bench Press > Competition Deadlift",
                "exercises": [
                    "Competition Squat",
                    "Competition Bench Press",
                    "Competition Deadlift",
                ],
            }
        ],
    }


def _template_options() -> dict[str, list[dict[str, Any]]]:
    assets = _load_assets()
    templates = assets.get("templates")

    if not isinstance(templates, dict) or not templates:
        return _fallback_templates()

    return templates


@block_factory_bp.get("/programming/factory")
def wizard():
    athletes = Athlete.query.order_by(
        Athlete.first_name.asc(), Athlete.last_name.asc()
    ).all()
    templates = _template_options()

    return render_template(
        "programming/factory.html",
        athletes=athletes,
        template_types=sorted(templates.keys()),
    )


@block_factory_bp.post("/programming/factory")
def generate():
    athlete_id = request.form.get("athlete_id", type=int)
    athlete = db.session.get(Athlete, athlete_id)

    if athlete is None:
        abort(404)

    name = request.form.get("name", "").strip() or "Generated Block"
    week_count = request.form.get("week_count", type=int) or 4
    training_days = request.form.get("training_days", type=int) or 4
    template_type = request.form.get("template_type", "SBD").strip().upper()

    week_count = max(1, min(24, week_count))
    training_days = max(1, min(7, training_days))

    templates = _template_options()
    candidates = templates.get(template_type) or _fallback_templates().get("SBD", [])

    if not candidates:
        abort(400)

    block = TrainingBlock(
        athlete=athlete,
        name=name,
    )
    db.session.add(block)
    db.session.flush()

    for week_position in range(1, week_count + 1):
        week = TrainingWeek(
            block=block,
            name=f"Week {week_position}",
            position=week_position,
        )
        db.session.add(week)
        db.session.flush()

        for day_position in range(1, training_days + 1):
            candidate = candidates[(day_position - 1) % len(candidates)]
            exercises = candidate.get("exercises")

            if not isinstance(exercises, list) or not exercises:
                signature = str(candidate.get("signature", ""))
                exercises = [
                    item.strip() for item in signature.split(">") if item.strip()
                ]

            session = TrainingSession(
                week=week,
                name=f"Day {day_position} · {template_type}",
                day_label=f"Day {day_position}",
                position=day_position,
            )
            db.session.add(session)
            db.session.flush()

            for exercise_position, exercise_name in enumerate(exercises, start=1):
                db.session.add(
                    ExercisePrescription(
                        session=session,
                        exercise_name=str(exercise_name),
                        position=exercise_position,
                        sets=1 if exercise_position == 1 else 3,
                        reps="5" if exercise_position == 1 else "8",
                        rpe=6.0 + min(2.0, (week_position - 1) * 0.5),
                    )
                )

    db.session.commit()

    return redirect(url_for("programming.block", block_id=block.id))
