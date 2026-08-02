from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
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


@dataclass(frozen=True)
class FactoryRequest:
    athlete_id: int
    name: str
    week_count: int
    training_days: int
    split: str
    goal: str
    squat_frequency: int
    bench_frequency: int
    deadlift_frequency: int
    deadlift_style: str
    meet_date: date | None


GOAL_RPE = {
    "hypertrophy": (6.0, 7.5),
    "development": (6.0, 8.0),
    "strength": (6.5, 8.5),
    "peaking": (7.0, 9.0),
    "offseason": (6.0, 7.5),
}

GOAL_REPS = {
    "hypertrophy": ("8", "10"),
    "development": ("5", "8"),
    "strength": ("3", "6"),
    "peaking": ("1", "4"),
    "offseason": ("6", "10"),
}

DEFAULT_SPLITS = {
    "S": ["S"],
    "B": ["B"],
    "D": ["D"],
    "SB": ["SB"],
    "BD": ["BD"],
    "SBD": ["SBD"],
    "UPPER_LOWER": ["SB", "BD"],
    "POWERLIFTING_3": ["SBD", "B", "D"],
    "POWERLIFTING_4": ["SB", "BD", "B", "SBD"],
    "POWERLIFTING_5": ["SB", "BD", "B", "S", "D"],
}


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
        "S": [
            {
                "signature": "Competition Squat > Leg Extension",
                "exercises": ["Competition Squat", "Leg Extension"],
            }
        ],
        "B": [
            {
                "signature": "Competition Bench Press > Cable Row",
                "exercises": ["Competition Bench Press", "Cable Row"],
            }
        ],
        "D": [
            {
                "signature": "Competition Deadlift > Romanian Deadlift",
                "exercises": ["Competition Deadlift", "Romanian Deadlift"],
            }
        ],
        "SB": [
            {
                "signature": (
                    "Competition Squat > Competition Bench Press > Cable Row"
                ),
                "exercises": [
                    "Competition Squat",
                    "Competition Bench Press",
                    "Cable Row",
                ],
            }
        ],
        "BD": [
            {
                "signature": (
                    "Competition Bench Press > Competition Deadlift > Leg Curl"
                ),
                "exercises": [
                    "Competition Bench Press",
                    "Competition Deadlift",
                    "Leg Curl",
                ],
            }
        ],
        "SBD": [
            {
                "signature": (
                    "Competition Squat > Competition Bench Press > Competition Deadlift"
                ),
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


def _parse_date(value: str) -> date | None:
    value = value.strip()
    return date.fromisoformat(value) if value else None


def _parse_factory_request() -> FactoryRequest:
    athlete_id = request.form.get("athlete_id", type=int)
    if athlete_id is None:
        abort(400)

    goal = request.form.get("goal", "development").strip().lower()
    if goal not in GOAL_RPE:
        goal = "development"

    split = request.form.get("split", "POWERLIFTING_4").strip().upper()
    if split not in DEFAULT_SPLITS:
        split = "POWERLIFTING_4"

    week_count = request.form.get("week_count", type=int) or 4
    training_days = request.form.get("training_days", type=int) or 4

    return FactoryRequest(
        athlete_id=athlete_id,
        name=request.form.get("name", "").strip() or "Generated Block",
        week_count=max(1, min(24, week_count)),
        training_days=max(1, min(7, training_days)),
        split=split,
        goal=goal,
        squat_frequency=max(
            0,
            min(5, request.form.get("squat_frequency", type=int) or 2),
        ),
        bench_frequency=max(
            0,
            min(7, request.form.get("bench_frequency", type=int) or 3),
        ),
        deadlift_frequency=max(
            0,
            min(3, request.form.get("deadlift_frequency", type=int) or 1),
        ),
        deadlift_style=request.form.get(
            "deadlift_style",
            "conventional",
        ).strip(),
        meet_date=_parse_date(request.form.get("meet_date", "")),
    )


def _day_sequence(factory: FactoryRequest) -> list[str]:
    default = DEFAULT_SPLITS[factory.split]

    if len(default) >= factory.training_days:
        return default[: factory.training_days]

    sequence = []

    while len(sequence) < factory.training_days:
        sequence.extend(default)

    return sequence[: factory.training_days]


def _candidate_exercises(
    templates: dict[str, list[dict[str, Any]]],
    day_type: str,
    day_index: int,
) -> list[str]:
    candidates = templates.get(day_type)

    if not candidates:
        candidates = _fallback_templates().get(day_type, [])

    if not candidates:
        candidates = _fallback_templates()["SBD"]

    candidate = candidates[day_index % len(candidates)]
    exercises = candidate.get("exercises")

    if isinstance(exercises, list) and exercises:
        return [str(item).strip() for item in exercises if str(item).strip()]

    signature = str(candidate.get("signature", ""))

    return [item.strip() for item in signature.split(">") if item.strip()]


def _apply_deadlift_style(
    exercises: list[str],
    style: str,
) -> list[str]:
    if style not in {"sumo", "conventional"}:
        return exercises

    result = []

    for exercise in exercises:
        lowered = exercise.lower()

        if "competition deadlift" in lowered or lowered == "deadlift":
            prefix = "Sumo" if style == "sumo" else "Conventional"
            result.append(f"{prefix} Deadlift")
        else:
            result.append(exercise)

    return result


def _week_rpe(
    factory: FactoryRequest,
    week_position: int,
) -> float:
    start, end = GOAL_RPE[factory.goal]

    if factory.week_count == 1:
        return start

    progress = (week_position - 1) / (factory.week_count - 1)
    value = start + ((end - start) * progress)

    if factory.goal != "peaking" and week_position == factory.week_count:
        value = max(start, value - 1.0)

    return round(value * 2) / 2


def _sets_and_reps(
    factory: FactoryRequest,
    exercise_position: int,
) -> tuple[int, str]:
    main_reps, accessory_reps = GOAL_REPS[factory.goal]

    if exercise_position == 1:
        if factory.goal == "peaking":
            return 1, main_reps
        if factory.goal == "strength":
            return 4, main_reps
        return 3, main_reps

    if exercise_position <= 3:
        return 3, accessory_reps

    return 2, accessory_reps


def _preview(factory: FactoryRequest) -> list[dict[str, Any]]:
    templates = _template_options()
    days = _day_sequence(factory)

    preview = []

    for day_index, day_type in enumerate(days):
        exercises = _candidate_exercises(
            templates,
            day_type,
            day_index,
        )
        exercises = _apply_deadlift_style(
            exercises,
            factory.deadlift_style,
        )

        preview.append(
            {
                "day": day_index + 1,
                "day_type": day_type,
                "exercises": exercises,
            }
        )

    return preview


@block_factory_bp.get("/programming/factory")
def wizard():
    selected_athlete_id = request.args.get("athlete_id", type=int)
    selected_athlete = (
        db.session.get(Athlete, selected_athlete_id)
        if selected_athlete_id is not None
        else None
    )
    athletes = Athlete.query.order_by(
        Athlete.first_name.asc(),
        Athlete.last_name.asc(),
    ).all()

    return render_template(
        "programming/factory.html",
        athletes=athletes,
        preview=None,
        form={},
        selected_athlete=selected_athlete,
    )


@block_factory_bp.post("/programming/factory/preview")
def preview():
    factory = _parse_factory_request()
    athlete = db.session.get(Athlete, factory.athlete_id)

    if athlete is None:
        abort(404)

    athletes = Athlete.query.order_by(
        Athlete.first_name.asc(),
        Athlete.last_name.asc(),
    ).all()

    return render_template(
        "programming/factory.html",
        athletes=athletes,
        preview=_preview(factory),
        form=request.form,
        selected_athlete=athlete,
    )


@block_factory_bp.post("/programming/factory")
def generate():
    factory = _parse_factory_request()
    athlete = db.session.get(Athlete, factory.athlete_id)

    if athlete is None:
        abort(404)

    templates = _template_options()
    days = _day_sequence(factory)

    block = TrainingBlock(
        athlete=athlete,
        name=factory.name,
    )
    db.session.add(block)
    db.session.flush()

    for week_position in range(1, factory.week_count + 1):
        week = TrainingWeek(
            block=block,
            name=f"Week {week_position}",
            position=week_position,
        )
        db.session.add(week)
        db.session.flush()

        week_rpe = _week_rpe(factory, week_position)

        for day_index, day_type in enumerate(days):
            exercises = _candidate_exercises(
                templates,
                day_type,
                day_index,
            )
            exercises = _apply_deadlift_style(
                exercises,
                factory.deadlift_style,
            )

            session = TrainingSession(
                week=week,
                name=f"Day {day_index + 1} · {day_type}",
                day_label=f"Day {day_index + 1}",
                position=day_index + 1,
            )
            db.session.add(session)
            db.session.flush()

            for exercise_position, exercise_name in enumerate(
                exercises,
                start=1,
            ):
                sets, reps = _sets_and_reps(
                    factory,
                    exercise_position,
                )

                db.session.add(
                    ExercisePrescription(
                        session=session,
                        exercise_name=exercise_name,
                        position=exercise_position,
                        sets=sets,
                        reps=reps,
                        rpe=week_rpe
                        if exercise_position == 1
                        else min(9.0, week_rpe + 0.5),
                    )
                )

    db.session.commit()

    return redirect(url_for("programming.block", block_id=block.id))
