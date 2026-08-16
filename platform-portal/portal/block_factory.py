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
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from .models.warmup import WarmupAssignment, WarmupProtocol, WarmupProtocolStep
from .programming_services.revisions import append_revision
from .services.accessory_intelligence import AccessoryIntelligence
from .services.exposure_intelligence import weekly_exposure_intents
from .services.programming_athlete_state import aggregate_programming_athlete_state
from .services.proposal_explanations import ProposalExplanationService
from .services.weekly_programming_intelligence import WeeklyProgrammingIntelligence
from .tenancy import athlete_query_for_request, require_athlete_access

block_factory_bp = Blueprint("block_factory", __name__)

FACTORY_WARMUPS = {
    "session-general": (
        "Session general preparation",
        ((10, "Raise body temperature", "duration", 1, None, 300),),
    ),
    "squat": (
        "Squat preparation",
        ((30, "Squat pattern preparation", "reps", 2, 8, None),
         (40, "Empty bar squat", "barbell", 2, 5, None)),
    ),
    "bench": (
        "Bench preparation",
        ((30, "Bench pattern preparation", "reps", 2, 8, None),
         (40, "Empty bar bench", "barbell", 2, 8, None)),
    ),
    "deadlift": (
        "Deadlift preparation",
        ((30, "Deadlift pattern preparation", "reps", 2, 8, None),
         (40, "Empty bar deadlift", "barbell", 2, 5, None)),
    ),
}


def _factory_warmup_protocols() -> dict[str, WarmupProtocol]:
    """Return the pinned, versioned defaults used by accepted factory proposals."""
    protocols: dict[str, WarmupProtocol] = {}
    for target, (name, steps) in FACTORY_WARMUPS.items():
        stable_key = f"factory-{target}"
        protocol = WarmupProtocol.query.filter_by(stable_key=stable_key, version=1).one_or_none()
        if protocol is None:
            protocol = WarmupProtocol(stable_key=stable_key, version=1, name=name)
            for position, (phase, step_name, kind, sets, reps, duration) in enumerate(steps, 1):
                protocol.steps.append(WarmupProtocolStep(
                    position=position, phase=phase, name=step_name, kind=kind,
                    sets=sets, reps=reps, duration_seconds=duration,
                    load_kg=20 if kind == "barbell" else None,
                ))
            db.session.add(protocol)
            db.session.flush()
        protocols[target] = protocol
    return protocols


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
    accessory_mode: str = "automatic"
    accessory_volume: str = "medium"
    deadlift_grip: str = "mixed"
    grip_work_priority: str = "none"
    training_strap_usage: str = "none"


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
    accessory_mode = request.form.get("accessory_mode", "automatic").strip().lower()
    if accessory_ids:
        accessory_mode = "manual"
    elif accessory_mode not in {"automatic", "none"}:
        accessory_mode = "automatic"
    accessory_volume = request.form.get("accessory_volume", "medium").strip().lower()
    if accessory_volume not in {"low", "medium", "high"}:
        accessory_volume = "medium"
    deadlift_grip = request.form.get("deadlift_grip", "mixed").strip().lower()
    if deadlift_grip not in {"hook", "mixed", "double-overhand", "straps", "other"}:
        deadlift_grip = "other"
    grip_work_priority = request.form.get("grip_work_priority", "none").strip().lower()
    if grip_work_priority not in {"none", "maintain", "build", "priority"}:
        grip_work_priority = "none"
    training_strap_usage = request.form.get("training_strap_usage", "none").strip().lower()
    if training_strap_usage not in {"none", "some", "most"}:
        training_strap_usage = "none"
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
        accessory_mode=accessory_mode,
        accessory_volume=accessory_volume,
        deadlift_grip=deadlift_grip,
        grip_work_priority=grip_work_priority,
        training_strap_usage=training_strap_usage,
    )


def _frequency_error(message: str) -> ValueError:
    return ValueError(f"Invalid weekly frequency: {message}")


def _validate_frequency_request(factory: FactoryRequest) -> None:
    if factory.training_days not in range(1, 8):
        raise _frequency_error("training days must be between 1 and 7.")

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

    # This established six-day distribution is coach-reviewed golden output.
    # Keep it stable while the general scheduler handles every other valid
    # combination deterministically.
    if (
        factory.training_days,
        factory.squat_frequency,
        factory.bench_frequency,
        factory.deadlift_frequency,
    ) == (6, 2, 5, 2):
        return ["B", "SD", "B", "B", "B", "SBD"]

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
        canonical.append("Competition Bench Press")

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
    days = _day_sequence(factory)
    exposure_intents = weekly_exposure_intents(
        days, goal=factory.goal, deadlift_style=factory.deadlift_style
    )

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
    intelligence = AccessoryIntelligence()
    athlete = db.session.get(Athlete, factory.athlete_id)
    programming_state = (
        aggregate_programming_athlete_state(athlete) if athlete is not None else {}
    )
    excluded_constraint_tags = set(
        programming_state.get("consumer_hints", {}).get(
            "excluded_constraint_tags", []
        )
    )
    suggested_ids: set[int] = set()
    fatigue_budget = intelligence.VOLUME_FATIGUE_BUDGETS[factory.accessory_volume]
    for day_index, day_type in enumerate(days):
        # Scheduling chooses when a lift occurs; coaching intent chooses what the
        # exposure is and how it is prescribed.
        intents = exposure_intents[day_index]
        exercises = [intent.exercise_name for intent in intents]
        main_count = len(day_type)
        main_exercises = exercises[:main_count]
        main_exercises = _adapt_main_exercises(
            factory.athlete_id,
            day_type,
            main_exercises,
            excluded_constraint_tags,
        )
        # Pinned selections replace automatic volume behaviour, are distributed
        # once across exposure-led days, and remain in coach order.
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
                    "provenance": "coach_selected",
                }
            )

        if factory.accessory_mode == "automatic" and not selected_accessories:
            family_by_code = {"S": "squat", "B": "bench", "D": "deadlift"}
            candidates = intelligence.candidates(
                phase=factory.goal,
                lift_families={family_by_code[code] for code in day_type},
                excluded_constraint_tags=excluded_constraint_tags,
                exclude_ids=suggested_ids,
                athlete_id=factory.athlete_id,
            )
            if (
                "D" in day_type
                and factory.grip_work_priority == "none"
                and factory.deadlift_grip != "hook"
            ):
                candidates = [
                    item for item in candidates
                    if (item.exercise.category or "").casefold() != "grip"
                ]
            if "D" in day_type and (
                factory.grip_work_priority != "none"
                or factory.deadlift_grip == "hook"
            ):
                grip = intelligence.grip_candidates(
                    phase=factory.goal,
                    competition_grip=factory.deadlift_grip,
                    strap_usage=factory.training_strap_usage,
                    priority=factory.grip_work_priority,
                    exclude_ids=suggested_ids,
                    athlete_id=factory.athlete_id,
                )
                grip_ids = {item.exercise.id for item in grip}
                candidates = grip + [
                    item for item in candidates if item.exercise.id not in grip_ids
                ]
            for suggestion in intelligence.select_for_volume(
                candidates, volume=factory.accessory_volume
            ):
                suggested_ids.add(suggestion.exercise.id)
                generated_accessories.append(
                    {
                        "id": suggestion.exercise.id,
                        "name": suggestion.exercise.name,
                        "role": _accessory_role(
                            {
                                "name": suggestion.exercise.name,
                                "category": suggestion.exercise.category,
                                "primary_muscles": suggestion.exercise.primary_muscles,
                                "technical_purposes": suggestion.exercise.technical_purposes,
                            }
                        ),
                        "source": "Library suggestion",
                        "provenance": "generated",
                        "reasons": suggestion.reasons,
                        "state_score": suggestion.state_score,
                        "state_provenance": suggestion.provenance,
                    }
                )

        if selected_accessories:
            accessory_outcome = "coach_selected"
            accessory_outcome_reason = "Pinned coach choices replace suggestions."
        elif factory.accessory_mode == "none":
            accessory_outcome = "intentional_none"
            accessory_outcome_reason = "The coach selected no assistance."
        elif generated_accessories:
            accessory_outcome = "automatic_selected"
            accessory_outcome_reason = (
                "Automatic assistance filled the available fatigue budget from "
                "eligible catalogue candidates."
            )
        else:
            accessory_outcome = "no_eligible_candidates"
            accessory_outcome_reason = (
                "No unused active, accessory-suitable catalogue candidates met "
                "this day's metadata constraints and fatigue budget."
            )

        preview.append(
            {
                "day": day_index + 1,
                "day_type": day_type,
                "exercises": main_exercises
                + [item["name"] for item in generated_accessories],
                "main_count": main_count,
                "exposures": [asdict(intent) for intent in intents],
                "accessories": generated_accessories,
                "accessory_count": len(generated_accessories),
                "accessory_outcome": accessory_outcome,
                "accessory_outcome_reason": accessory_outcome_reason,
                "accessory_range": (
                    f"{factory.accessory_volume} volume · {fatigue_budget}-unit fatigue budget"
                    if factory.accessory_mode == "automatic"
                    and not selected_accessories else "coach selected only"
                ),
            }
        )

    return preview


def _metadata_set(value: str | None) -> set[str]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return set()
    return {
        str(item).strip().casefold()
        for item in parsed
        if isinstance(parsed, list) and str(item).strip()
    } if isinstance(parsed, list) else set()


def _adapt_main_exercises(
    athlete_id: int,
    day_type: str,
    names: list[str],
    excluded_tags: set[str],
) -> list[str]:
    """Choose a supported non-conflicting variation; coach selections win."""
    families = {"S": "squat", "B": "bench", "D": "deadlift"}
    normalised_tags = {tag.casefold() for tag in excluded_tags}
    now = datetime.now(UTC).replace(tzinfo=None)
    selections: dict[str, str] = {}
    for row in AthleteStateOverride.query.filter(
        AthleteStateOverride.athlete_id == athlete_id,
        AthleteStateOverride.target_type == "programming",
        AthleteStateOverride.revoked_at.is_(None),
        (AthleteStateOverride.expires_at.is_(None)) | (AthleteStateOverride.expires_at > now),
    ).order_by(AthleteStateOverride.recorded_at.asc(), AthleteStateOverride.id.asc()):
        payload = row.override_json if isinstance(row.override_json, dict) else {}
        choices = payload.get("exercise_selections")
        if isinstance(choices, dict):
            for family, name in choices.items():
                if family in families.values() and isinstance(name, str) and name.strip():
                    selections[family] = name.strip()

    result: list[str] = []
    for code, current_name in zip(day_type, names):
        family = families[code]
        coach_name = selections.get(family)
        if coach_name:
            result.append(coach_name)
            continue
        current = Exercise.query.filter_by(name=current_name, active=True).one_or_none()
        if not normalised_tags or current is None or not (
            _metadata_set(current.constraint_tags) & normalised_tags
        ):
            result.append(current_name)
            continue
        alternatives = Exercise.query.filter_by(
            lift_family=family, active=True
        ).order_by(Exercise.specificity.desc(), Exercise.name.asc(), Exercise.id.asc()).all()
        replacement = next(
            (
                item for item in alternatives
                if item.name != current_name
                and not (_metadata_set(item.constraint_tags) & normalised_tags)
            ),
            None,
        )
        result.append(replacement.name if replacement is not None else current_name)
    return result


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


PROPOSAL_TYPE = "weekly_programming_v7"
ACCEPTED_PROPOSAL_TYPES = {"weekly_programming_v6", PROPOSAL_TYPE}
PROPOSAL_VERSION = "programming-v7-1"


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
    explanation: Any,
) -> dict[str, Any]:
    return {
        "factory": _json_value(asdict(factory)),
        "preview": _json_value(scheduled_preview),
        "source_context": _json_value(asdict(intelligence.data)),
        "volume_progression": _json_value(asdict(intelligence.volume)),
        "explanation": _json_value(asdict(explanation)),
        "generator_version": PROPOSAL_VERSION,
    }


def _reference_block(athlete_id: int) -> dict[str, Any] | None:
    block = (
        TrainingBlock.query.filter_by(athlete_id=athlete_id)
        .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
        .first()
    )
    if block is None:
        return None
    exercises = sorted(
        {
            prescription.exercise_name
            for week in block.weeks
            for session in week.sessions
            for prescription in session.prescriptions
            if prescription.lift_slot_id is not None
        },
        key=lambda value: (value.casefold(), value),
    )
    return {"id": block.id, "name": block.name, "exercises": exercises}


def _proposal_explanation(
    factory: FactoryRequest, scheduled_preview: list[dict[str, Any]], intelligence: Any
) -> Any:
    # The curve reports prescribed working sets, not tonnage (loads are RPE-led).
    exercise_names = {
        name for day in scheduled_preview for name in day["exercises"]
    }
    default_sets = {
        exercise.name: exercise.default_sets
        for exercise in Exercise.query.filter(Exercise.name.in_(exercise_names)).all()
        if exercise.default_sets is not None
    }
    weekly_sets = sum(
        default_sets.get(name, _sets_and_reps(factory, position)[0])
        if position > int(day["main_count"])
        else _sets_and_reps(factory, position)[0]
        for day in scheduled_preview
        for position, name in enumerate(day["exercises"], start=1)
    )
    return ProposalExplanationService().build(
        factory=factory,
        weekly_structure=intelligence.weekly_structure,
        context=intelligence.data,
        rpe_values=[
            _week_rpe(factory, week) for week in range(1, factory.week_count + 1)
        ],
        volume_values=[weekly_sets] * factory.week_count,
        reference_block=_reference_block(factory.athlete_id),
        assistance_reasons={
            item["name"]: tuple(item.get("reasons") or ())
            for day in scheduled_preview
            for item in day.get("accessories", ())
        },
    )


def _factory_from_payload(payload: dict[str, Any]) -> FactoryRequest:
    values = dict(payload["factory"])
    values["meet_date"] = (
        date.fromisoformat(values["meet_date"]) if values.get("meet_date") else None
    )
    values["accessory_exercise_ids"] = tuple(values.get("accessory_exercise_ids") or ())
    values.setdefault("accessory_mode", "automatic")
    values.setdefault("accessory_volume", "medium")
    values.setdefault("deadlift_grip", "mixed")
    values.setdefault("grip_work_priority", "none")
    values.setdefault("training_strap_usage", "none")
    return FactoryRequest(**values)


def _load_proposal() -> tuple[AthleteStateRecommendation, dict[str, Any]]:
    proposal_id = request.form.get("proposal_id", type=int)
    supplied_integrity = request.form.get("proposal_integrity", "")
    if proposal_id is None:
        abort(400, description="A previewed proposal is required before acceptance.")
    proposal = db.session.get(AthleteStateRecommendation, proposal_id)
    if (
        proposal is None
        or proposal.recommendation_type not in ACCEPTED_PROPOSAL_TYPES
    ):
        abort(404)
    require_athlete_access(proposal.athlete_id)
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
        require_athlete_access(selected_athlete_id)
        if selected_athlete_id is not None
        else None
    )
    athletes = athlete_query_for_request().order_by(
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
    try:
        factory = _parse_factory_request()
    except ValueError:
        abort(400, description="Factory dates and numeric inputs must be valid.")
    athlete = require_athlete_access(factory.athlete_id)
    factory = _apply_active_coach_overrides(factory)

    athletes = athlete_query_for_request().order_by(
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

    explanation = _proposal_explanation(
        factory, scheduled_preview, intelligence_preview
    )
    payload = _proposal_payload(
        factory, scheduled_preview, intelligence_preview, explanation
    )
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
        explanation=explanation,
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
    athlete = require_athlete_access(proposal.athlete_id)

    try:
        scheduled_preview = _preview(factory)
        intelligence = WeeklyProgrammingIntelligence().preview(
            factory, athlete, scheduled_preview
        )
    except ValueError as error:
        abort(409, description=f"Proposal is stale: {error}")
    explanation = _proposal_explanation(factory, scheduled_preview, intelligence)
    current_payload = _proposal_payload(
        factory, scheduled_preview, intelligence, explanation
    )
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
    warmup_protocols = _factory_warmup_protocols()

    for week_position in range(1, factory.week_count + 1):
        week = TrainingWeek(
            block=block,
            name=f"Week {week_position}",
            position=week_position,
        )
        db.session.add(week)
        db.session.flush()

        volume_week = intelligence.volume.weeks[week_position - 1]
        # The intelligence envelope owns bounded readiness/adherence caps. A
        # later coach-authored cap in that envelope remains authoritative.
        week_rpe = volume_week.target_rpe
        exposure_seen = {family: 0 for family in ("squat", "bench", "deadlift")}
        exposure_totals = {
            "squat": factory.squat_frequency,
            "bench": factory.bench_frequency,
            "deadlift": factory.deadlift_frequency,
        }

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
            db.session.add(WarmupAssignment(
                protocol_id=warmup_protocols["session-general"].id,
                athlete_id=athlete.id, session_id=session.id,
                reason="Factory-generated session preparation",
            ))

            exercise_rows = {
                item.name: item
                for item in Exercise.query.filter(Exercise.name.in_(exercises)).all()
            }
            main_count = int(day["main_count"])
            accessory_by_name = {
                item["name"]: item for item in day.get("accessories", [])
            }
            family_by_code = {"S": "squat", "B": "bench", "D": "deadlift"}
            main_families = [family_by_code[code] for code in day_type]
            main_intents = list(day.get("exposures", []))

            for exercise_position, exercise_name in enumerate(
                exercises,
                start=1,
            ):
                sets, reps = _sets_and_reps(
                    factory,
                    exercise_position,
                )

                slot = None
                slot_role = None
                provenance = accessory_by_name.get(exercise_name, {}).get(
                    "provenance", "coach_selected"
                )
                if exercise_position <= main_count:
                    family = main_families[exercise_position - 1]
                    intent = main_intents[exercise_position - 1]
                    # Preserve athlete-state volume behaviour for a single weekly
                    # exposure. At higher frequencies, the explicit role profile
                    # owns the session prescription and never creates zero-set work.
                    if exposure_totals[family] == 1:
                        sets = volume_week.sbd_sets[family]
                    else:
                        sets = max(1, int(intent["sets"]))
                    reps = str(intent["reps"])
                    slot = ProgrammingLiftSlot(
                        session=session,
                        position=exercise_position,
                        lift_family=family,
                        exposure_role=intent["role"],
                    )
                    db.session.add(slot)
                    db.session.flush()
                    db.session.add(WarmupAssignment(
                        protocol_id=warmup_protocols[family].id,
                        athlete_id=athlete.id, session_id=session.id,
                        lift_slot_id=slot.id,
                        reason=f"Factory-generated {family} preparation",
                    ))
                    slot_role = "top_set"
                    provenance = "generated"

                exercise_row = exercise_rows.get(exercise_name)
                if exercise_position > main_count and exercise_row is not None:
                    sets = exercise_row.default_sets or sets
                    reps = exercise_row.default_reps or reps
                db.session.add(
                    ExercisePrescription(
                        session=session,
                        exercise=exercise_row,
                        lift_slot=slot,
                        slot_role=slot_role,
                        provenance=provenance,
                        exercise_name=exercise_name,
                        position=exercise_position,
                        sets=sets,
                        reps=reps,
                        prescription_type="rpe",
                        rpe=max(
                            1.0,
                            min(
                                10.0,
                                week_rpe
                                + float(
                                    main_intents[exercise_position - 1]["rpe_offset"]
                                ),
                            ),
                        )
                        if exercise_position <= main_count
                        else min(9.0, week_rpe + 0.5),
                        notes=(
                            main_intents[exercise_position - 1]["purpose"]
                            if exercise_position <= main_count else None
                        ),
                    )
                )

    append_revision(block, change_type="factory_programme_created", summary="Created programme from accepted factory proposal", reason=proposal.rationale)
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
