from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from sqlalchemy import or_

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
from .models.exercise_library import Exercise
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
    accessory_exercise_ids: tuple[int, ...] = ()
    accessory_volume: str = "standard"
    accessory_count_min: int | None = None
    accessory_count_max: int | None = None
    accessory_emphasis: tuple[str, ...] = ()


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

ACCESSORY_DAY = "ACCESSORY"

ACCESSORY_VOLUME_RANGES = {
    "minimal": (1, 2),
    "standard": (3, 4),
    "high": (5, 6),
}
ACCESSORY_EMPHASES = {
    "quads", "posterior_chain", "chest", "shoulders", "triceps",
    "lats_upper_back", "trunk", "gpp",
}

# Roles are deliberately ordered.  The selector cycles through this plan before
# adding a second exercise from the same role or movement pattern.
DAY_ROLE_PLANS = {
    "S": ("secondary strength", "hypertrophy", "unilateral", "trunk/bracing", "balancing", "GPP / mobility"),
    "B": ("secondary strength", "balancing", "hypertrophy", "trunk/bracing", "unilateral", "GPP / mobility"),
    "D": ("secondary strength", "hypertrophy", "balancing", "trunk/bracing", "unilateral", "GPP / mobility"),
    "COMBINED": ("balancing", "hypertrophy", "trunk/bracing", "unilateral", "GPP / mobility", "secondary strength"),
    ACCESSORY_DAY: ("hypertrophy", "balancing", "unilateral", "trunk/bracing", "GPP / mobility", "secondary strength"),
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
        ACCESSORY_DAY: [
            {
                "signature": "Cable Row > Leg Curl",
                "exercises": ["Cable Row", "Leg Curl"],
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


def _form_int_or_default(name: str, default: int) -> int:
    value = request.form.get(name, type=int)
    return default if value is None else value


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

    week_count = _form_int_or_default("week_count", 4)
    training_days = _form_int_or_default("training_days", 4)

    accessory_ids = tuple(
        value for value in request.form.getlist("accessory_exercise_id", type=int)
        if value is not None
    )
    accessory_volume = request.form.get("accessory_volume", "standard").strip().lower()
    if accessory_volume not in {*ACCESSORY_VOLUME_RANGES, "custom"}:
        accessory_volume = "standard"
    count_min = request.form.get("accessory_count_min", type=int)
    count_max = request.form.get("accessory_count_max", type=int)
    emphasis = tuple(
        item for item in request.form.getlist("accessory_emphasis")
        if item in ACCESSORY_EMPHASES
    )
    return FactoryRequest(
        athlete_id=athlete_id,
        name=request.form.get("name", "").strip() or "Generated Block",
        week_count=max(1, min(24, week_count)),
        training_days=training_days,
        split=split,
        goal=goal,
        squat_frequency=_form_int_or_default("squat_frequency", 2),
        bench_frequency=_form_int_or_default("bench_frequency", 3),
        deadlift_frequency=_form_int_or_default("deadlift_frequency", 1),
        deadlift_style=request.form.get(
            "deadlift_style",
            "conventional",
        ).strip(),
        meet_date=_parse_date(request.form.get("meet_date", "")),
        accessory_exercise_ids=accessory_ids,
        accessory_volume=accessory_volume,
        accessory_count_min=count_min,
        accessory_count_max=count_max,
        accessory_emphasis=emphasis,
    )


def _frequency_error(message: str) -> ValueError:
    return ValueError(f"Invalid weekly frequency: {message}")


def _validate_frequency_request(factory: FactoryRequest) -> None:
    if factory.training_days not in {3, 4, 5}:
        raise _frequency_error("training days must be 3, 4, or 5.")

    frequencies = {
        "Squat": factory.squat_frequency,
        "Bench": factory.bench_frequency,
        "Deadlift": factory.deadlift_frequency,
    }
    for lift, frequency in frequencies.items():
        if frequency < 0:
            raise _frequency_error(f"{lift} frequency cannot be negative.")
        if frequency > factory.training_days:
            raise _frequency_error(
                f"{lift} frequency ({frequency}) exceeds the "
                f"{factory.training_days} training days."
            )

    if not any(frequencies.values()):
        raise _frequency_error(
            "select at least one squat, bench, or deadlift exposure."
        )


def _evenly_spaced_days(
    frequency: int,
    training_days: int,
    offset: int = 0,
) -> set[int]:
    """Return deterministic, evenly distributed zero-based training-day indexes."""
    if frequency == 0:
        return set()

    return {
        ((position * training_days) // frequency + offset) % training_days
        for position in range(frequency)
    }


def _day_sequence(factory: FactoryRequest) -> list[str]:
    """Build one weekly schedule whose primary lift counts match the request."""
    _validate_frequency_request(factory)

    exposures = {
        "S": _evenly_spaced_days(
            factory.squat_frequency,
            factory.training_days,
        ),
        "B": _evenly_spaced_days(
            factory.bench_frequency,
            factory.training_days,
        ),
        # A single deadlift exposure is placed away from the first session.
        "D": _evenly_spaced_days(
            factory.deadlift_frequency,
            factory.training_days,
            offset=1,
        ),
    }

    sequence = []
    for day_index in range(factory.training_days):
        day_type = "".join(
            lift for lift in ("S", "B", "D") if day_index in exposures[lift]
        )
        sequence.append(day_type or ACCESSORY_DAY)

    return sequence


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


def _ensure_main_lifts(
    exercises: list[str],
    day_type: str,
    deadlift_style: str,
) -> list[str]:
    """Return exactly the main lifts scheduled for this day."""
    scheduled_lifts = (
        set()
        if day_type == ACCESSORY_DAY
        else {code for code in day_type if code in {"S", "B", "D"}}
    )

    canonical: list[str] = []

    if "S" in scheduled_lifts:
        canonical.append("Competition Squat")

    if "B" in scheduled_lifts:
        canonical.append("Competition Bench Press")

    if "D" in scheduled_lifts:
        canonical.append(
            "Sumo Deadlift" if deadlift_style == "sumo" else "Conventional Deadlift"
        )

    def movement_code(name: str) -> str | None:
        lowered = name.casefold().strip()

        if "squat" in lowered:
            return "S"

        if "bench" in lowered:
            return "B"

        if "deadlift" in lowered or "romanian" in lowered or lowered == "rdl":
            return "D"

        return None

    # Strip mined S/B/D variants, then add back only scheduled main lifts.
    accessories = [name for name in exercises if movement_code(name) is None]

    return canonical + accessories


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


def _accessory_target(factory: FactoryRequest, day_type: str) -> tuple[int, int]:
    """Return the explicit, bounded accessory range shown in the preview."""
    if factory.accessory_volume == "custom":
        minimum = factory.accessory_count_min
        maximum = factory.accessory_count_max
        if minimum is None:
            raise ValueError("Custom accessory volume requires a count.")
        maximum = minimum if maximum is None else maximum
        if not 0 <= minimum <= maximum <= 10:
            raise ValueError("Custom accessory count must be between 0 and 10.")
        return minimum, maximum

    minimum, maximum = ACCESSORY_VOLUME_RANGES[factory.accessory_volume]
    if factory.accessory_volume == "standard":
        # Explicit lift-aware defaults take precedence over the general 3–4.
        if day_type == "B":
            return 4, 5
        if day_type not in {"S", "D", ACCESSORY_DAY}:
            return 2, 4
    return minimum, maximum


def _text_values(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _accessory_role(item: dict[str, Any]) -> str:
    text = " ".join(
        _text_values(item.get(key))
        for key in ("name", "family", "category", "primary_muscles")
    ).casefold()
    if any(word in text for word in ("plank", "core", "ab ", "abdominal", "pallof", "carry", "trunk")):
        return "trunk/bracing"
    if any(word in text for word in ("single-arm", "single-leg", "unilateral", "split squat", "lunge", "step-up", "b-stance")):
        return "unilateral"
    if any(word in text for word in ("sled", "prowler", "bike", "rower", "mobility", "rehab", "prehab", "walk")):
        return "GPP / mobility"
    if any(word in text for word in ("row", "pulldown", "pull-up", "chin-up", "face pull", "rear delt", "back")):
        return "balancing"
    if any(word in text for word in ("close-grip", "pause", "tempo", "pin ", "press", "leg press", "hack squat")):
        return "secondary strength"
    return "hypertrophy"


def _movement_pattern(item: dict[str, Any]) -> str:
    text = " ".join(
        _text_values(item.get(key))
        for key in ("name", "family", "category", "primary_muscles")
    ).casefold()
    patterns = (
        ("row", ("row",)), ("vertical pull", ("pulldown", "pull-up", "chin-up")),
        ("quad", ("quad", "leg extension", "leg press", "hack squat")),
        ("hinge", ("deadlift", "rdl", "romanian", "good morning", "back extension")),
        ("hamstring", ("leg curl", "hamstring")), ("press", ("press", "chest", "triceps")),
        ("shoulder", ("delt", "lateral raise", "shoulder")),
        ("trunk", ("plank", "core", "abdominal", "pallof", "carry", "trunk")),
        ("unilateral leg", ("lunge", "split squat", "step-up")),
        ("gpp", ("sled", "prowler", "bike", "rower", "mobility", "walk")),
    )
    for pattern, words in patterns:
        if any(word in text for word in words):
            return pattern
    return str(item.get("family") or item.get("category") or item.get("name")).casefold()


def _lower_back_heavy(item: dict[str, Any]) -> bool:
    text = f"{item.get('name', '')} {item.get('family', '')}".casefold()
    return int(item.get("fatigue_rating") or 3) >= 4 or any(
        word in text for word in ("good morning", "barbell row", "pendlay", "back extension", "romanian deadlift")
    )


def _emphasis_score(item: dict[str, Any], emphases: tuple[str, ...]) -> int:
    if not emphases:
        return 0
    text = " ".join(_text_values(item.get(key)) for key in (
        "name", "family", "category", "primary_muscles", "secondary_muscles"
    )).casefold()
    terms = {
        "quads": ("quad", "leg extension", "leg press", "hack squat"),
        "posterior_chain": ("hamstring", "glute", "leg curl", "hip thrust"),
        "chest": ("chest", "pec"), "shoulders": ("shoulder", "delt"),
        "triceps": ("triceps", "close-grip"),
        "lats_upper_back": ("lat", "back", "row", "pulldown", "pull-up"),
        "trunk": ("trunk", "core", "plank", "pallof", "carry", "abdominal"),
        "gpp": ("sled", "prowler", "bike", "rower", "carry", "walk"),
    }
    return sum(1 for emphasis in emphases if any(term in text for term in terms[emphasis]))


def _accessory_pool() -> list[dict[str, Any]]:
    """Merge active catalogue records with compatible intelligence aliases."""
    assets = _load_assets()
    by_name: dict[str, dict[str, Any]] = {}
    for item in assets.get("exercises", []):
        if isinstance(item, dict) and item.get("accessory_suitable"):
            by_name[str(item.get("name", "")).casefold()] = item
    rows = Exercise.query.filter(
        Exercise.active.is_(True),
        or_(Exercise.accessory_suitable.is_(True), Exercise.movement == "accessory"),
    ).all()
    for row in rows:
        by_name[row.name.casefold()] = {
            "name": row.name, "family": row.family, "category": row.category,
            "movement": row.movement, "primary_muscles": row.primary_muscles,
            "secondary_muscles": row.secondary_muscles, "fatigue_rating": row.fatigue_rating,
            "aliases": row.aliases, "accessory_suitable": True,
        }
    return sorted(by_name.values(), key=lambda item: str(item.get("name", "")).casefold())


def _select_accessories(
    factory: FactoryRequest,
    day_type: str,
    template_accessories: list[str],
    manual_accessories: list[str],
    pool: list[dict[str, Any]],
    weekly_usage: dict[str, int],
) -> list[dict[str, str]]:
    minimum, maximum = _accessory_target(factory, day_type)
    # Manual ordering is inviolate. A coach may intentionally exceed the target.
    selected_names: list[str] = []
    for name in manual_accessories:
        if name.casefold() not in {item.casefold() for item in selected_names}:
            selected_names.append(name)
    target = max(minimum, len(selected_names))
    target = min(maximum, target) if len(selected_names) <= maximum else len(selected_names)

    pool_by_name = {str(item.get("name", "")).casefold(): item for item in pool}
    # Mined template choices remain the first automatic candidates, but never
    # displace a coach choice and still pass duplicate/fatigue guards.
    ranked = []
    for index, item in enumerate(pool):
        key = str(item.get("name", "")).casefold()
        template_rank = next((i for i, name in enumerate(template_accessories) if name.casefold() == key), 999)
        ranked.append((
            weekly_usage.get(key, 0),
            -_emphasis_score(item, factory.accessory_emphasis),
            template_rank,
            index,
            item,
        ))
    ranked.sort(key=lambda row: row[:-1])

    plan_key = day_type if day_type in {"S", "B", "D", ACCESSORY_DAY} else "COMBINED"
    roles = DAY_ROLE_PLANS[plan_key]
    used_patterns: set[str] = set()
    lower_back_count = 0
    selected: list[dict[str, str]] = []
    for name in selected_names:
        item = pool_by_name.get(name.casefold(), {"name": name})
        selected.append({"name": name, "role": _accessory_role(item), "source": "Coach selected"})
        used_patterns.add(_movement_pattern(item))
        lower_back_count += int(_lower_back_heavy(item))

    for desired_role in roles:
        if len(selected) >= target:
            break
        for row in ranked:
            item = row[-1]
            name = str(item.get("name", "")).strip()
            key = name.casefold()
            pattern = _movement_pattern(item)
            if not name or key in {choice["name"].casefold() for choice in selected}:
                continue
            if _accessory_role(item) != desired_role or pattern in used_patterns:
                continue
            if _lower_back_heavy(item) and (lower_back_count or "D" in day_type):
                continue
            selected.append({"name": name, "role": desired_role, "source": "Generated"})
            used_patterns.add(pattern)
            lower_back_count += int(_lower_back_heavy(item))
            break

    # Sparse catalogues can lack a role. Fill deterministically while retaining
    # duplicate and lumbar-fatigue safeguards.
    for row in ranked:
        if len(selected) >= target:
            break
        item = row[-1]
        name = str(item.get("name", "")).strip()
        key = name.casefold()
        pattern = _movement_pattern(item)
        if not name or key in {choice["name"].casefold() for choice in selected}:
            continue
        if pattern in used_patterns:
            continue
        if _lower_back_heavy(item) and (lower_back_count or "D" in day_type):
            continue
        selected.append({"name": name, "role": _accessory_role(item), "source": "Generated"})
        used_patterns.add(pattern)
        lower_back_count += int(_lower_back_heavy(item))

    for choice in selected:
        key = choice["name"].casefold()
        weekly_usage[key] = weekly_usage.get(key, 0) + 1
    # Retain the established contract that pinned choices form the final,
    # contiguous ordered section of each session.
    return (
        [choice for choice in selected if choice["source"] == "Generated"]
        + [choice for choice in selected if choice["source"] == "Coach selected"]
    )


def _preview(factory: FactoryRequest) -> list[dict[str, Any]]:
    templates = _template_options()
    days = _day_sequence(factory)

    preview = []
    selected_accessories = []
    if factory.accessory_exercise_ids:
        if len(factory.accessory_exercise_ids) != len(set(factory.accessory_exercise_ids)):
            raise ValueError("The same coach-selected accessory cannot be added twice.")
        rows = Exercise.query.filter(
            Exercise.id.in_(factory.accessory_exercise_ids),
            Exercise.active.is_(True),
        ).all()
        by_id = {item.id: item.name for item in rows}
        if len(by_id) != len(set(factory.accessory_exercise_ids)):
            raise ValueError("One or more selected accessories are unavailable.")
        selected_accessories = [by_id[item_id] for item_id in factory.accessory_exercise_ids]

    pool = _accessory_pool()
    weekly_usage: dict[str, int] = {}
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
        exercises = _ensure_main_lifts(
            exercises,
            day_type,
            factory.deadlift_style,
        )
        main_count = 0 if day_type == ACCESSORY_DAY else len(day_type)
        main_exercises = exercises[:main_count]
        generated_accessories = _select_accessories(
            factory,
            day_type,
            exercises[main_count:],
            selected_accessories,
            pool,
            weekly_usage,
        )
        minimum, maximum = _accessory_target(factory, day_type)

        preview.append(
            {
                "day": day_index + 1,
                "day_type": day_type,
                "exercises": main_exercises + [item["name"] for item in generated_accessories],
                "main_count": main_count,
                "accessories": generated_accessories,
                "accessory_count": len(generated_accessories),
                "accessory_range": f"{minimum}–{maximum}" if minimum != maximum else str(minimum),
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
    accessory_exercises = Exercise.query.filter(
        Exercise.active.is_(True),
        or_(Exercise.accessory_suitable.is_(True), Exercise.movement == "accessory"),
    ).order_by(Exercise.category.asc(), Exercise.name.asc()).all()

    return render_template(
        "programming/factory.html",
        athletes=athletes,
        preview=None,
        form={},
        selected_athlete=selected_athlete,
        accessory_exercises=accessory_exercises,
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
    accessory_exercises = Exercise.query.filter(
        Exercise.active.is_(True),
        or_(Exercise.accessory_suitable.is_(True), Exercise.movement == "accessory"),
    ).order_by(Exercise.category.asc(), Exercise.name.asc()).all()

    try:
        scheduled_preview = _preview(factory)
    except ValueError as error:
        abort(400, description=str(error))

    return render_template(
        "programming/factory.html",
        athletes=athletes,
        preview=scheduled_preview,
        form=request.form,
        selected_athlete=athlete,
        accessory_exercises=accessory_exercises,
    )


@block_factory_bp.post("/programming/factory")
def generate():
    factory = _parse_factory_request()
    athlete = db.session.get(Athlete, factory.athlete_id)

    if athlete is None:
        abort(404)

    try:
        scheduled_preview = _preview(factory)
    except ValueError as error:
        abort(400, description=str(error))

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

        for day in scheduled_preview:
            day_index = int(day["day"]) - 1
            day_type = str(day["day_type"])
            exercises = list(day["exercises"])

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
