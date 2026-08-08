from __future__ import annotations

import hashlib
import hmac
import itertools
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from .extensions import db
from .models.athlete import Athlete
from .models.athlete_state import AthleteStateOverride, AthleteStateRecommendation
from .models.exercise_library import Exercise
from .models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from .services.weekly_programming_intelligence import WeeklyProgrammingIntelligence

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
                "exercises": ["Competition Bench", "Cable Row"],
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
                    "Competition Bench",
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
                    "Competition Bench",
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
                    "Competition Bench",
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
        value
        for value in request.form.getlist("accessory_exercise_id", type=int)
        if value is not None
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
    if sum(frequencies.values()) < factory.training_days:
        raise _frequency_error(
            "there are not enough squat, bench, and deadlift exposures to anchor "
            "every training day; reduce training days or add an exposure."
        )


def _day_sequence(factory: FactoryRequest) -> list[str]:
    """Build one weekly schedule whose primary lift counts match the request."""
    _validate_frequency_request(factory)

    indexes = range(factory.training_days)
    choices = (
        itertools.combinations(indexes, factory.squat_frequency),
        itertools.combinations(indexes, factory.bench_frequency),
        itertools.combinations(indexes, factory.deadlift_frequency),
    )
    candidates = []
    for squat_days, bench_days, deadlift_days in itertools.product(*choices):
        exposure_sets = {
            "S": set(squat_days),
            "B": set(bench_days),
            "D": set(deadlift_days),
        }
        loads = [
            sum(day in values for values in exposure_sets.values()) for day in indexes
        ]
        if 0 in loads:
            continue
        sequence = tuple(
            "".join(lift for lift in ("S", "B", "D") if day in exposure_sets[lift])
            for day in indexes
        )
        candidates.append((max(loads), sum(value * value for value in loads), sequence))
    if not candidates:
        raise _frequency_error(
            "the requested exposures cannot anchor every training day."
        )
    return list(min(candidates)[2])


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
    scheduled_lifts = {code for code in day_type if code in {"S", "B", "D"}}

    canonical: list[str] = []

    if "S" in scheduled_lifts:
        canonical.append("Competition Squat")

    if "B" in scheduled_lifts:
        canonical.append("Competition Bench")

    if "D" in scheduled_lifts:
        canonical.append(
            "Sumo Deadlift" if deadlift_style == "sumo" else "Conventional Deadlift"
        )

    # Day codes are the exposure source of truth. Template tail entries are not
    # silently promoted to assistance.
    return canonical


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


def _text_values(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value or "")


def _accessory_role(item: dict[str, Any]) -> str:
    technical_purposes = _text_values(item.get("technical_purposes")).casefold()
    if "trunk" in technical_purposes or "bracing" in technical_purposes:
        return "trunk/bracing"
    if "hypertrophy" in technical_purposes:
        return "hypertrophy"
    if "technique" in technical_purposes or "strength" in technical_purposes:
        return "secondary strength"
    text = " ".join(
        _text_values(item.get(key))
        for key in ("name", "family", "category", "primary_muscles")
    ).casefold()
    if any(
        word in text
        for word in ("plank", "core", "ab ", "abdominal", "pallof", "carry", "trunk")
    ):
        return "trunk/bracing"
    if any(
        word in text
        for word in (
            "single-arm",
            "single-leg",
            "unilateral",
            "split squat",
            "lunge",
            "step-up",
            "b-stance",
        )
    ):
        return "unilateral"
    if any(
        word in text
        for word in (
            "sled",
            "prowler",
            "bike",
            "rower",
            "mobility",
            "rehab",
            "prehab",
            "walk",
        )
    ):
        return "GPP / mobility"
    if any(
        word in text
        for word in (
            "row",
            "pulldown",
            "pull-up",
            "chin-up",
            "face pull",
            "rear delt",
            "back",
        )
    ):
        return "balancing"
    if any(
        word in text
        for word in (
            "close-grip",
            "pause",
            "tempo",
            "pin ",
            "press",
            "leg press",
            "hack squat",
        )
    ):
        return "secondary strength"
    return "hypertrophy"


def _accessory_pool() -> list[dict[str, Any]]:
    """Merge active catalogue records with compatible intelligence aliases."""
    assets = _load_assets()
    by_name: dict[str, dict[str, Any]] = {}
    for item in assets.get("exercises", []):
        if isinstance(item, dict) and item.get("accessory_suitable"):
            by_name[str(item.get("name", "")).casefold()] = item
    rows = Exercise.query.filter(
        Exercise.active.is_(True),
        Exercise.accessory_suitable.is_(True),
    ).all()
    for row in rows:
        by_name[row.name.casefold()] = {
            "name": row.name,
            "family": row.family,
            "category": row.category,
            "movement": row.movement,
            "primary_muscles": row.primary_muscles,
            "secondary_muscles": row.secondary_muscles,
            "fatigue_rating": row.fatigue_rating,
            "aliases": row.aliases,
            "accessory_suitable": True,
            "lift_family": row.lift_family,
            "movement_pattern": row.movement_pattern,
            "specificity": row.specificity,
            "technical_purposes": row.technical_purposes,
            "equipment_options": row.equipment_options,
            "constraint_tags": row.constraint_tags,
            "variation_of": row.variation_of,
            "swap_group": row.swap_group,
        }
    return sorted(
        by_name.values(), key=lambda item: str(item.get("name", "")).casefold()
    )


def _preview(factory: FactoryRequest) -> list[dict[str, Any]]:
    templates = _template_options()
    days = _day_sequence(factory)

    preview = []
    selected_accessories = []
    if factory.accessory_exercise_ids:
        if len(factory.accessory_exercise_ids) != len(
            set(factory.accessory_exercise_ids)
        ):
            raise ValueError("The same coach-selected accessory cannot be added twice.")
        rows = Exercise.query.filter(
            Exercise.id.in_(factory.accessory_exercise_ids),
            Exercise.active.is_(True),
            Exercise.accessory_suitable.is_(True),
        ).all()
        by_id = {item.id: item.name for item in rows}
        if len(by_id) != len(set(factory.accessory_exercise_ids)):
            raise ValueError("One or more selected accessories are unavailable.")
        selected_accessories = [
            by_id[item_id] for item_id in factory.accessory_exercise_ids
        ]

    pool = _accessory_pool()
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
        main_count = len(day_type)
        main_exercises = exercises[:main_count]
        # Intelligence never fills an accessory quota. Pinned coach selections
        # are distributed once across exposure-led days and remain in coach order.
        manual_for_day = selected_accessories[day_index :: len(days)]
        generated_accessories = []
        for name in manual_for_day:
            item = next(
                (
                    item
                    for item in pool
                    if str(item.get("name", "")).casefold() == name.casefold()
                ),
                {"name": name},
            )
            generated_accessories.append(
                {
                    "name": name,
                    "role": _accessory_role(item),
                    "source": "Coach selected",
                }
            )

        preview.append(
            {
                "day": day_index + 1,
                "day_type": day_type,
                "exercises": main_exercises
                + [item["name"] for item in generated_accessories],
                "main_count": main_count,
                "accessories": generated_accessories,
                "accessory_count": len(generated_accessories),
                "accessory_range": "coach selected only",
            }
        )

    return preview


def _apply_active_coach_overrides(factory: FactoryRequest) -> FactoryRequest:
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = AthleteStateOverride.query.filter(
        AthleteStateOverride.athlete_id == factory.athlete_id,
        AthleteStateOverride.target_type == "programming",
        AthleteStateOverride.revoked_at.is_(None),
        (
            AthleteStateOverride.expires_at.is_(None)
            | (AthleteStateOverride.expires_at > now)
        ),
    ).order_by(AthleteStateOverride.recorded_at.asc(), AthleteStateOverride.id.asc())
    supported = {
        "training_days",
        "squat_frequency",
        "bench_frequency",
        "deadlift_frequency",
        "goal",
        "deadlift_style",
    }
    values: dict[str, Any] = {}
    for row in rows:
        if isinstance(row.override_json, dict):
            for key, value in row.override_json.items():
                if key not in supported:
                    continue
                if key in {
                    "training_days",
                    "squat_frequency",
                    "bench_frequency",
                    "deadlift_frequency",
                } and (isinstance(value, bool) or not isinstance(value, int)):
                    continue
                if key == "goal" and value not in GOAL_RPE:
                    continue
                if key == "deadlift_style" and value not in {"sumo", "conventional"}:
                    continue
                values[key] = value
    return replace(factory, **values) if values else factory


PROPOSAL_TYPE = "weekly_programming_v6"
PROPOSAL_VERSION = "programming-v6-1"


def _actor() -> str:
    user = g.get("current_user")
    if user is not None:
        return str(user.email)
    if current_app.testing and current_app.config["AUTHENTICATION_DISABLED"]:
        return "test-coach"
    abort(401)


def _json_value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _proposal_integrity(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    secret = str(current_app.secret_key).encode()
    return hmac.new(secret, encoded, hashlib.sha256).hexdigest()


def _proposal_payload(
    factory: FactoryRequest,
    scheduled_preview: list[dict[str, Any]],
    intelligence: Any,
) -> dict[str, Any]:
    return {
        "factory": _json_value(asdict(factory)),
        "preview": _json_value(scheduled_preview),
        "source_context": _json_value(asdict(intelligence.data)),
        "generator_version": PROPOSAL_VERSION,
    }


def _factory_from_payload(payload: dict[str, Any]) -> FactoryRequest:
    values = dict(payload["factory"])
    values["meet_date"] = (
        date.fromisoformat(values["meet_date"]) if values.get("meet_date") else None
    )
    values["accessory_exercise_ids"] = tuple(values.get("accessory_exercise_ids") or ())
    return FactoryRequest(**values)


def _load_proposal() -> tuple[AthleteStateRecommendation, dict[str, Any]]:
    proposal_id = request.form.get("proposal_id", type=int)
    supplied_integrity = request.form.get("proposal_integrity", "")
    if proposal_id is None:
        abort(400, description="A previewed proposal is required before acceptance.")
    proposal = db.session.get(AthleteStateRecommendation, proposal_id)
    if proposal is None or proposal.recommendation_type != PROPOSAL_TYPE:
        abort(404)
    payload = proposal.recommendation_json
    expected = _proposal_integrity(payload)
    if not hmac.compare_digest(expected, supplied_integrity):
        abort(409, description="Proposal integrity check failed; preview again.")
    return proposal, payload


def _mark_decided(proposal: AthleteStateRecommendation, status: str) -> bool:
    updated = AthleteStateRecommendation.query.filter_by(
        id=proposal.id, status="proposed"
    ).update(
        {"status": status, "decided_at": datetime.now(UTC), "decided_by": _actor()},
        synchronize_session=False,
    )
    if updated != 1:
        db.session.rollback()
        return False
    return True


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
    accessory_exercises = (
        Exercise.query.filter(
            Exercise.active.is_(True),
            Exercise.accessory_suitable.is_(True),
        )
        .order_by(Exercise.category.asc(), Exercise.name.asc())
        .all()
    )

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
    factory = _apply_active_coach_overrides(factory)

    athletes = Athlete.query.order_by(
        Athlete.first_name.asc(),
        Athlete.last_name.asc(),
    ).all()
    accessory_exercises = (
        Exercise.query.filter(
            Exercise.active.is_(True),
            Exercise.accessory_suitable.is_(True),
        )
        .order_by(Exercise.category.asc(), Exercise.name.asc())
        .all()
    )

    try:
        scheduled_preview = _preview(factory)
        intelligence_preview = WeeklyProgrammingIntelligence().preview(
            factory, athlete, scheduled_preview
        )
    except ValueError as error:
        abort(400, description=str(error))

    payload = _proposal_payload(factory, scheduled_preview, intelligence_preview)
    previous_id = request.form.get("proposal_id", type=int)
    proposal_override = None
    if previous_id is not None:
        previous = db.session.get(AthleteStateRecommendation, previous_id)
        if (
            previous is None
            or previous.status != "proposed"
            or previous.athlete_id != athlete.id
        ):
            abort(
                409,
                description="The proposal is stale or already decided; start a new preview.",
            )
        supplied = request.form.get("proposal_integrity", "")
        if not hmac.compare_digest(
            _proposal_integrity(previous.recommendation_json), supplied
        ):
            abort(409, description="Proposal integrity check failed; preview again.")
        reason = request.form.get("override_reason", "").strip()
        if previous.recommendation_json != payload and not reason:
            abort(
                400,
                description="Editing a generated proposal requires a coach override reason.",
            )
        if previous.recommendation_json != payload:
            proposal_override = AthleteStateOverride(
                athlete_id=athlete.id,
                target_type="programming_proposal",
                target_ref=str(previous.id),
                override_json={"replacement": payload},
                reason=reason,
                recorded_by=_actor(),
            )
            db.session.add(proposal_override)
        previous.status = "superseded"
        previous.decided_at = datetime.now(UTC)
        previous.decided_by = _actor()
    proposal = AthleteStateRecommendation(
        athlete_id=athlete.id,
        recommendation_type=PROPOSAL_TYPE,
        recommendation_json=payload,
        rationale="WeeklyProgrammingIntelligence preview; no athlete data was inferred.",
        signal_ids_json=[],
        generator_version=PROPOSAL_VERSION,
        status="proposed",
    )
    db.session.add(proposal)
    db.session.commit()
    integrity = _proposal_integrity(payload)

    return render_template(
        "programming/factory.html",
        athletes=athletes,
        preview=scheduled_preview,
        intelligence=intelligence_preview,
        form=request.form,
        selected_athlete=athlete,
        accessory_exercises=accessory_exercises,
        proposal=proposal,
        proposal_integrity=integrity,
        proposal_override=proposal_override,
    )


@block_factory_bp.post("/programming/factory")
def generate():
    proposal, payload = _load_proposal()
    if proposal.status != "proposed":
        abort(409, description="Proposal was already decided and cannot be replayed.")
    factory = _factory_from_payload(payload)
    athlete = db.session.get(Athlete, proposal.athlete_id)

    if athlete is None:
        abort(404)

    try:
        scheduled_preview = _preview(factory)
        intelligence = WeeklyProgrammingIntelligence().preview(
            factory, athlete, scheduled_preview
        )
    except ValueError as error:
        abort(409, description=f"Proposal is stale: {error}")
    current_payload = _proposal_payload(factory, scheduled_preview, intelligence)
    if current_payload != payload:
        abort(
            409,
            description="Proposal is stale because its source data changed; preview again.",
        )
    if not _mark_decided(proposal, "accepted"):
        abort(409, description="Proposal was already decided and cannot be replayed.")

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


@block_factory_bp.post("/programming/factory/proposal/dismiss")
def dismiss_proposal():
    proposal, _payload = _load_proposal()
    if proposal.status != "proposed":
        abort(409, description="Proposal was already decided and cannot be replayed.")
    if not _mark_decided(proposal, "dismissed"):
        abort(409, description="Proposal was already decided and cannot be replayed.")
    db.session.commit()
    return redirect(url_for("block_factory.wizard", athlete_id=proposal.athlete_id))
