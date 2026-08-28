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
from .programming_services.revisions import append_revision, authored_snapshot
from .services.accessory_intelligence import AccessoryIntelligence
from .services.exposure_intelligence import weekly_exposure_intents
from .services.golden_programmes import golden_programmes
from .services.prescription_planner import PrescriptionContext, PrescriptionPlanner
from .services.variation_selector import VariationContext, VariationSelector
from .services.athlete_state import latest_facts
from .services.programming_athlete_state import (
    accessory_readiness_multiplier,
    aggregate_programming_athlete_state,
)
from .services.proposal_explanations import ProposalExplanationService
from .services.weekly_programming_intelligence import WeeklyProgrammingIntelligence
from .services.weekly_planner import WeeklyPlanner
from .services.weekly_accessory_planner import (
    WeeklyAccessoryCandidate,
    WeeklyAccessoryContext,
    WeeklyAccessoryPlanner,
)
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
    "POWERLIFTING_6": ["B", "SD", "B", "B", "B", "SBD"],
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


def _legacy_day_sequence(factory: FactoryRequest) -> list[str]:
    """Compatibility schedule for out-of-policy historical requests."""
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


def _day_sequence(factory: FactoryRequest) -> list[str]:
    """Compatibility projection of the coaching-led weekly skeleton.

    Historical callers can still render requests outside Wave 3's supported
    coaching bounds; new proposals never use that fallback.
    """
    try:
        return WeeklyPlanner().plan(
            training_days=factory.training_days,
            squat_frequency=factory.squat_frequency,
            bench_frequency=factory.bench_frequency,
            deadlift_frequency=factory.deadlift_frequency,
            goal=factory.goal,
        ).day_sequence
    except ValueError:
        return _legacy_day_sequence(factory)


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
    """Legacy rendering helper; not authoritative for new prescriptions."""
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
    _validate_frequency_request(factory)
    # WeeklyPlanner is authoritative for new proposals.  _day_sequence remains
    # a compatibility helper for historical rendering and direct legacy calls.
    weekly_structure = WeeklyPlanner().plan(
        training_days=factory.training_days,
        squat_frequency=factory.squat_frequency,
        bench_frequency=factory.bench_frequency,
        deadlift_frequency=factory.deadlift_frequency,
        goal=factory.goal,
    )
    days = weekly_structure.day_sequence
    exposure_intents = weekly_exposure_intents(
        weekly_structure, goal=factory.goal, deadlift_style=factory.deadlift_style
    )
    variation_selector = VariationSelector()

    preview: list[dict[str, Any]] = []
    selected_rows: list[Exercise] = []
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
        by_id = {item.id: item for item in rows}
        if len(by_id) != len(set(factory.accessory_exercise_ids)):
            raise ValueError("One or more selected accessories are unavailable.")
        selected_rows = [by_id[item_id] for item_id in factory.accessory_exercise_ids]

    athlete = db.session.get(Athlete, factory.athlete_id)
    programming_state = (
        aggregate_programming_athlete_state(athlete) if athlete is not None else {}
    )
    readiness = accessory_readiness_multiplier(programming_state)
    excluded_constraint_tags = set(
        programming_state.get("consumer_hints", {}).get(
            "excluded_constraint_tags", []
        )
    )
    for day_index, day_type in enumerate(days):
        # Scheduling chooses when a lift occurs; coaching intent chooses what the
        # exposure is and how it is prescribed.
        intents = exposure_intents[day_index]
        selections = [variation_selector.select(VariationContext(
            lift_family=intent.lift_family,
            purpose=intent.purpose,
            stress_role=intent.stress_role,
            # Competition deadlift style is an explicit coach input, not a
            # catalogue inference. Other known mappings remain conservative.
            available_exercises=((intent.exercise_name,)
                                 if intent.purpose == "competition" else ()),
        )) for intent in intents]
        exercises = [selection.exercise_name for selection in selections]
        main_count = len(day_type)
        main_exercises = exercises[:main_count]
        main_exercises, adaptation_reviews, exercise_provenance = _adapt_main_exercises(
            factory.athlete_id,
            day_type,
            main_exercises,
            excluded_constraint_tags,
        )
        exposure_metadata = [asdict(intent) for intent in intents]
        for index, exercise_name in enumerate(main_exercises):
            exposure_metadata[index]["exercise_name"] = exercise_name
            exposure_metadata[index]["exercise_provenance"] = exercise_provenance[index]
            exposure_metadata[index]["variation_reason"] = selections[index].reason
            exposure_metadata[index]["variation_provenance"] = selections[index].provenance
        preview.append(
            {
                "day": day_index + 1,
                "day_type": day_type,
                "weekly_planner_reason": weekly_structure.days[day_index].reason,
                "weekly_planner_provenance": list(weekly_structure.reasons),
                "exercises": main_exercises,
                "main_count": main_count,
                "exposures": exposure_metadata,
                "coach_review_required": bool(adaptation_reviews),
                "coach_review_reasons": adaptation_reviews,
                "accessories": [],
            }
        )

    if selected_rows:
        # Coach selection and prescription remain authoritative. Placement uses
        # the same session-load policy as automatic assistance.
        planner = WeeklyAccessoryPlanner()
        pinned_context = WeeklyAccessoryContext(
            goal=factory.goal, volume=factory.accessory_volume,
            week_count=factory.week_count, day_types=tuple(days),
            constraints=frozenset(tag.casefold() for tag in excluded_constraint_tags),
            readiness_multiplier=readiness, meet_date=factory.meet_date,
            competition_grip=factory.deadlift_grip,
            grip_work_priority=factory.grip_work_priority,
        )
        for planned in planner.place_pins(selected_rows, pinned_context):
            row = planned.exercise
            day = preview[planned.day_index]
            backstop_conflict = planner.constraint_conflict(row, pinned_context.constraints)
            item = {
                "id": row.id, "name": row.name,
                "role": _accessory_role(row.__dict__),
                "purpose": "coach-selected assistance",
                "source": "Coach selected", "provenance": "coach_selected",
                "reason": "Coach-pinned choice is authoritative.",
                "reasons": ("Coach-pinned choice is authoritative.",),
                "prescriptions": [asdict(value) for value in planned.prescriptions],
                "warnings": planned.warnings + (
                    ("Coach review: pin conflicts with the athlete's structured "
                     "loading constraints; the authoritative pin was preserved.",)
                    if backstop_conflict else ()
                ),
            }
            day["accessories"].append(item)
            if item["warnings"]:
                day["coach_review_required"] = True
                day["coach_review_reasons"].extend(item["warnings"])
    elif factory.accessory_mode == "automatic":
        observation_tags = {
            tag.casefold()
            for item in programming_state.get("soft_signals", [])
            for tag in (
                *item.get("effects", {}).get("assistance_preference_tags", []),
                item.get("effects", {}).get("technical_signal", ""),
                item.get("label", ""),
            )
            if tag
        }
        available_equipment = None
        equipment_fact = next((
            fact.value_json for key, fact in latest_facts(factory.athlete_id).items()
            if "equipment" in str(key).casefold()
        ), None)
        if isinstance(equipment_fact, (list, tuple, set)):
            available_equipment = frozenset(str(value).casefold() for value in equipment_fact)
        elif isinstance(equipment_fact, dict):
            values = equipment_fact.get("available") or equipment_fact.get("equipment")
            if isinstance(values, (list, tuple, set)):
                available_equipment = frozenset(str(value).casefold() for value in values)
        state_evaluation = AccessoryIntelligence().evaluate_candidates(
            phase=factory.goal,
            lift_families={
                {"S": "squat", "B": "bench", "D": "deadlift"}[code]
                for day_type in days for code in day_type
            },
            excluded_constraint_tags=excluded_constraint_tags,
            athlete_id=factory.athlete_id,
            session_tags=observation_tags,
        )
        plan = WeeklyAccessoryPlanner().plan(
            (
                WeeklyAccessoryCandidate(
                    suggestion.exercise,
                    suggestion.state_score,
                    suggestion.provenance,
                    suggestion.reasons,
                )
                for suggestion in state_evaluation.candidates
            ),
            WeeklyAccessoryContext(
                goal=factory.goal, volume=factory.accessory_volume,
                week_count=factory.week_count, day_types=tuple(days),
                constraints=frozenset(tag.casefold() for tag in excluded_constraint_tags),
                observations=frozenset(observation_tags),
                available_equipment=available_equipment,
                readiness_multiplier=readiness, meet_date=factory.meet_date,
                competition_grip=factory.deadlift_grip,
                grip_work_priority=factory.grip_work_priority,
            ),
        )
        for planned in plan:
            row = planned.exercise
            day = preview[planned.day_index]
            reasons = (*planned.state_reasons, planned.reason)
            if (row.category or "").casefold() == "grip":
                grip_reasons = []
                if factory.deadlift_grip == "hook" and factory.grip_work_priority == "none":
                    grip_reasons.append("hook-grip competition requirement")
                elif factory.grip_work_priority != "none":
                    grip_reasons.append(f"grip-work priority is {factory.grip_work_priority}")
                grip_reasons.append(f"competition grip is {factory.deadlift_grip}")
                reasons = (*planned.state_reasons, *grip_reasons)

            item = {
                "id": row.id, "name": row.name, "role": planned.purpose,
                "purpose": planned.purpose, "source": "Weekly planner",
                "provenance": "generated", "reason": planned.reason,
                "reasons": reasons,
                "state_score": planned.state_score,
                "state_provenance": planned.state_provenance,
                "state_reasons": planned.state_reasons,
                "prescriptions": [asdict(value) for value in planned.prescriptions],
            }
            day["accessories"].append(item)

    for day in preview:
        accessories = day["accessories"]
        day["exercises"].extend(item["name"] for item in accessories)
        day["accessory_count"] = len(accessories)
        if selected_rows:
            day["accessory_outcome"] = "coach_selected"
            day["accessory_outcome_reason"] = "Pinned coach choices replace automatic planning."
        elif factory.accessory_mode == "none":
            day["accessory_outcome"] = "intentional_none"
            day["accessory_outcome_reason"] = "The coach selected no assistance."
        elif accessories:
            day["accessory_outcome"] = "automatic_selected"
            day["accessory_outcome_reason"] = "Selected and placed by the authoritative weekly accessory planner."
        else:
            day["accessory_outcome"] = "no_eligible_candidates"
            day["accessory_outcome_reason"] = "No weekly candidate passed quality, state, redundancy, equipment, and fatigue gates."
        day["accessory_range"] = (
            f"{factory.accessory_volume} weekly fatigue plan"
            if factory.accessory_mode == "automatic" and not selected_rows
            else "coach selected only"
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
) -> tuple[list[str], list[str], list[str]]:
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
    reviews: list[str] = []
    provenance: list[str] = []
    for code, current_name in zip(day_type, names):
        family = families[code]
        coach_name = selections.get(family)
        if coach_name:
            result.append(coach_name)
            provenance.append("coach_selected")
            continue
        current = Exercise.query.filter_by(name=current_name, active=True).one_or_none()
        if not normalised_tags or current is None or not (
            _metadata_set(current.constraint_tags) & normalised_tags
        ):
            result.append(current_name)
            provenance.append("generated")
            continue
        # Constraint tags can reject a choice, but incomplete catalogue metadata
        # cannot safely nominate an arbitrary replacement. Preserve the known
        # mapping and make the unresolved decision explicit.
        result.append(current_name)
        provenance.append("requires_coach_review")
        reviews.append(
            f"No automatically compatible {family} alternative was available; "
            f"review {current_name} before acceptance."
        )
    return result, reviews, provenance


def _allocate_weekly_sets(
    weekly_total: int, intents: list[dict[str, Any]]
) -> list[int]:
    """Allocate an authoritative weekly envelope by role weight.

    Every exposure receives one set first. Remaining sets follow the relative
    role prescriptions using largest remainders, with stable exposure order as
    the tie-break. This preserves role differentiation without exceeding the
    weekly total.
    """
    count = len(intents)
    if count == 0:
        return []
    if weekly_total < count:
        raise ValueError(
            f"Weekly set envelope ({weekly_total}) cannot retain one set across "
            f"{count} scheduled exposures; coach review is required."
        )
    allocation = [1] * count
    remaining = weekly_total - count
    weights = [max(0, int(intent["sets"]) - 1) for intent in intents]
    weight_total = sum(weights)
    if not remaining or not weight_total:
        for index in range(remaining):
            allocation[index % count] += 1
        return allocation
    shares = [remaining * weight / weight_total for weight in weights]
    floors = [int(share) for share in shares]
    allocation = [value + floor for value, floor in zip(allocation, floors)]
    leftovers = weekly_total - sum(allocation)
    order = sorted(
        range(count), key=lambda index: (-(shares[index] - floors[index]), index)
    )
    for index in order[:leftovers]:
        allocation[index] += 1
    return allocation


def _effective_exposure_rpe(
    base_rpe: float, role_offset: float, effective_cap: float | None
) -> float:
    adjusted = max(1.0, min(10.0, base_rpe + role_offset))
    return min(effective_cap, adjusted) if effective_cap is not None else adjusted


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
        "accessory_exercise_ids",
        "accessory_mode",
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
                if key == "accessory_exercise_ids":
                    if not isinstance(value, (list, tuple)) or any(
                        isinstance(item, bool) or not isinstance(item, int)
                        for item in value
                    ):
                        continue
                    value = tuple(value)
                if key == "accessory_mode" and value not in {"automatic", "none"}:
                    continue
                values[key] = value
    return replace(factory, **values) if values else factory


PROPOSAL_TYPE = "weekly_programming_v7"
ACCEPTED_PROPOSAL_TYPES = {"weekly_programming_v6", PROPOSAL_TYPE}
PROPOSAL_VERSION = "programming-v10-purpose-led-planning"


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
        # This is the acceptance boundary.  Everything below is a final ORM-shaped
        # value chosen during preview; acceptance only validates and materializes it.
        "programme": _finalize_programme_graph(factory, scheduled_preview, intelligence),
        "source_token": _proposal_source_token(factory.athlete_id),
        "source_context": _json_value(asdict(intelligence.data)),
        "volume_progression": _json_value(asdict(intelligence.volume)),
        "explanation": _json_value(asdict(explanation)),
        "generator_version": PROPOSAL_VERSION,
    }


def _proposal_source_token(athlete_id: int) -> str:
    """Fingerprint proposal inputs without invoking programming intelligence."""
    tables = (
        "athletes", "athlete_state_facts", "coach_technical_observations",
        "athlete_constraint_flags", "athlete_state_overrides", "weekly_checkins",
        "training_session_logs", "training_set_results", "training_blocks",
        "exercises",
    )
    snapshot: dict[str, Any] = {}
    for name in tables:
        table = db.metadata.tables.get(name)
        if table is None:
            continue
        statement = db.select(table)
        if "athlete_id" in table.c:
            statement = statement.where(table.c.athlete_id == athlete_id)
        elif name == "athletes":
            statement = statement.where(table.c.id == athlete_id)
        elif name == "training_set_results":
            logs = db.metadata.tables["training_session_logs"]
            statement = statement.join(logs, table.c.session_log_id == logs.c.id).where(
                logs.c.athlete_id == athlete_id
            )
        rows = db.session.execute(statement.order_by(table.c.id)).mappings().all()
        snapshot[name] = [_json_value(dict(row)) for row in rows]
    snapshot["programmes"] = [
        authored_snapshot(block)
        for block in TrainingBlock.query.filter_by(athlete_id=athlete_id).order_by(
            TrainingBlock.id
        )
    ]
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _finalize_programme_graph(
    factory: FactoryRequest,
    scheduled_preview: list[dict[str, Any]],
    intelligence: Any,
) -> dict[str, Any]:
    """Apply the existing acceptance transformations before signing the proposal."""
    graph: dict[str, Any] = {"schema_version": 1, "block": {
        "name": factory.name, "objective": None, "status": "draft",
    }, "weeks": []}
    exercise_names = {name for day in scheduled_preview for name in day["exercises"]}
    exercise_rows = {
        item.name: item for item in Exercise.query.filter(Exercise.name.in_(exercise_names)).all()
    }
    prescription_planner = PrescriptionPlanner()
    for week_position in range(1, factory.week_count + 1):
        volume_week = intelligence.volume.weeks[week_position - 1]
        exposure_seen = {family: 0 for family in ("squat", "bench", "deadlift")}
        intents_by_family = {
            family: [intent for day in scheduled_preview for intent in day.get("exposures", [])
                     if intent["lift_family"] == family]
            for family in exposure_seen
        }
        allocations = {
            family: _allocate_weekly_sets(volume_week.sbd_sets[family], intents_by_family[family])
            for family in exposure_seen
        }
        week = {"name": f"Week {week_position}", "position": week_position,
                "notes": None, "sessions": []}
        for day in scheduled_preview:
            position = int(day["day"])
            day_type = str(day["day_type"])
            accessories = {item["name"]: item for item in day.get("accessories", [])}
            main_intents = list(day.get("exposures", []))
            families = [{"S": "squat", "B": "bench", "D": "deadlift"}[code]
                        for code in day_type]
            session = {
                "name": f"Day {position} · {day_type}", "day_label": f"Day {position}",
                "day_type": day_type, "position": position, "notes": None,
                "warmups": ["session-general"], "prescriptions": [],
            }
            for exercise_position, exercise_name in enumerate(day["exercises"], 1):
                sets, reps = _sets_and_reps(factory, exercise_position)
                row = exercise_rows.get(exercise_name)
                accessory = accessories.get(exercise_name)
                slot = None
                provenance = accessory.get("provenance", "coach_selected") if accessory else "coach_selected"
                notes = accessory.get("reason") if accessory else None
                week_accessory = None
                if exercise_position <= int(day["main_count"]):
                    family = families[exercise_position - 1]
                    intent = main_intents[exercise_position - 1]
                    allocation_index = exposure_seen[family]
                    sets = allocations[family][allocation_index]
                    exposure_seen[family] += 1
                    planned_prescription = prescription_planner.plan(PrescriptionContext(
                        purpose=str(intent["purpose"]),
                        stress_role=str(intent["stress_role"]),
                        phase=factory.goal,
                        week=week_position,
                        week_count=factory.week_count,
                        target_rpe=float(volume_week.target_rpe),
                        allocated_sets=sets,
                    ))
                    component = planned_prescription.components[0]
                    sets, reps = component.sets, component.reps
                    slot = {
                        "position": exercise_position,
                        "lift_family": family,
                        # Compatibility projection for the migration-free ORM.
                        "exposure_role": intent["legacy_role"],
                    }
                    # ORM provenance remains the migration-free compatibility
                    # projection; richer selector provenance is signed in the
                    # exposure metadata and explanation.
                    exercise_provenance = str(intent.get("exercise_provenance", "generated"))
                    provenance = (exercise_provenance
                                  if exercise_provenance == "coach_selected"
                                  else "generated")
                    notes = (f"{intent.get('variation_reason', intent['reason'])} "
                             f"{planned_prescription.reason}")
                    rpe = component.rpe
                    effective_cap = min(
                        value for value in (
                            volume_week.effective_rpe_cap, intent.get("rpe_cap")
                        ) if value is not None
                    ) if any(value is not None for value in (
                        volume_week.effective_rpe_cap, intent.get("rpe_cap")
                    )) else None
                    if effective_cap is not None:
                        rpe = min(float(effective_cap), rpe)
                    session["warmups"].append(family)
                else:
                    if row is not None:
                        sets, reps = row.default_sets or sets, row.default_reps or reps
                    if accessory and accessory.get("prescriptions"):
                        week_accessory = next((value for value in accessory["prescriptions"]
                                               if int(value["week"]) == week_position), None)
                    if week_accessory:
                        sets, reps = int(week_accessory["sets"]), str(week_accessory["reps"])
                    rpe = (float(week_accessory["rpe"]) if week_accessory else
                           min(9.0, row.default_rpe if row and row.default_rpe is not None
                               else volume_week.target_rpe + 0.5))
                session["prescriptions"].append({
                    "exercise_id": row.id if row else None, "exercise_name": exercise_name,
                    "position": exercise_position, "sets": sets, "reps": reps,
                    "prescription_type": "rpe", "rpe": rpe,
                    "rest_seconds": (int(week_accessory["rest_seconds"]) if week_accessory
                                     else row.default_rest_seconds if row else None),
                    "notes": notes, "provenance": provenance, "slot_role": "top_set" if slot else None,
                    "lift_slot": slot,
                })
            week["sessions"].append(session)
        graph["weeks"].append(week)
    return _json_value(graph)


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
        rpe_values=[week.target_rpe for week in intelligence.volume.weeks],
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
    if proposal.status != "proposed":
        abort(409, description="Proposal was already decided and cannot be replayed.")
    payload = proposal.recommendation_json
    if (
        not isinstance(payload, dict)
        or payload.get("generator_version") != proposal.generator_version
    ):
        abort(409, description="Proposal version check failed; preview again.")
    expected = _proposal_integrity(payload)
    if not hmac.compare_digest(expected, supplied_integrity):
        abort(409, description="Proposal integrity check failed; preview again.")
    return proposal, payload


def _validate_programme_graph(graph: Any) -> dict[str, Any]:
    """Validate signed persistence data without deriving or changing any value."""
    if not isinstance(graph, dict) or graph.get("schema_version") != 1:
        raise ValueError("Unsupported proposal programme graph")
    block = graph.get("block")
    weeks = graph.get("weeks")
    if not isinstance(block, dict) or not isinstance(block.get("name"), str) or not isinstance(weeks, list) or not weeks:
        raise ValueError("Proposal programme graph is incomplete")
    for week_position, week in enumerate(weeks, 1):
        if not isinstance(week, dict) or week.get("position") != week_position or not isinstance(week.get("sessions"), list):
            raise ValueError("Proposal week ordering is invalid")
        for session_position, session in enumerate(week["sessions"], 1):
            if not isinstance(session, dict) or session.get("position") != session_position:
                raise ValueError("Proposal session ordering is invalid")
            prescriptions = session.get("prescriptions")
            if not isinstance(prescriptions, list) or not prescriptions:
                raise ValueError("Proposal session prescriptions are invalid")
            for position, item in enumerate(prescriptions, 1):
                if not isinstance(item, dict) or item.get("position") != position:
                    raise ValueError("Proposal prescription ordering is invalid")
                if not isinstance(item.get("exercise_name"), str) or not item["exercise_name"].strip():
                    raise ValueError("Proposal exercise identity is invalid")
                if isinstance(item.get("sets"), bool) or not isinstance(item.get("sets"), int) or item["sets"] < 1:
                    raise ValueError("Proposal sets are invalid")
                rpe = item.get("rpe")
                if isinstance(rpe, bool) or not isinstance(rpe, (int, float)) or not 1 <= rpe <= 10:
                    raise ValueError("Proposal RPE is invalid")
                slot = item.get("lift_slot")
                if slot is not None:
                    if (not isinstance(slot, dict) or slot.get("position") != position
                            or slot.get("lift_family") not in {"squat", "bench", "deadlift"}):
                        raise ValueError("Proposal lift slot is invalid")
                    # The model validator deliberately includes historical readable roles.
                    ProgrammingLiftSlot(
                        position=position, lift_family=slot["lift_family"],
                        exposure_role=slot.get("exposure_role"),
                    ).validate()
    return graph


def _materialize_programme_graph(
    graph: dict[str, Any], athlete: Athlete
) -> TrainingBlock:
    block_data = graph["block"]
    block = TrainingBlock(
        athlete=athlete, name=block_data["name"],
        objective=block_data.get("objective"), status=block_data.get("status", "draft"),
    )
    db.session.add(block)
    db.session.flush()
    protocols = _factory_warmup_protocols()
    for week_data in graph["weeks"]:
        week = TrainingWeek(
            block=block, name=week_data["name"], position=week_data["position"],
            notes=week_data.get("notes"),
        )
        db.session.add(week)
        db.session.flush()
        for session_data in week_data["sessions"]:
            session = TrainingSession(
                week=week, name=session_data["name"], day_label=session_data.get("day_label"),
                position=session_data["position"], notes=session_data.get("notes"),
            )
            db.session.add(session)
            db.session.flush()
            db.session.add(WarmupAssignment(
                protocol_id=protocols["session-general"].id, athlete_id=athlete.id,
                session_id=session.id, reason="Factory-generated session preparation",
            ))
            for item in session_data["prescriptions"]:
                slot = None
                slot_data = item.get("lift_slot")
                if slot_data:
                    slot = ProgrammingLiftSlot(
                        session=session, position=slot_data["position"],
                        lift_family=slot_data["lift_family"],
                        exposure_role=slot_data.get("exposure_role"),
                    )
                    db.session.add(slot)
                    db.session.flush()
                    db.session.add(WarmupAssignment(
                        protocol_id=protocols[slot.lift_family].id, athlete_id=athlete.id,
                        session_id=session.id, lift_slot_id=slot.id,
                        reason=f"Factory-generated {slot.lift_family} preparation",
                    ))
                exercise = db.session.get(Exercise, item.get("exercise_id")) if item.get("exercise_id") else None
                if exercise is not None and exercise.name != item["exercise_name"]:
                    raise ValueError("Proposal exercise identity no longer matches")
                db.session.add(ExercisePrescription(
                    session=session, exercise=exercise, lift_slot=slot,
                    slot_role=item.get("slot_role"), provenance=item.get("provenance"),
                    exercise_name=item["exercise_name"], position=item["position"],
                    sets=item["sets"], reps=item.get("reps"),
                    prescription_type=item.get("prescription_type"), rpe=item["rpe"],
                    rest_seconds=item.get("rest_seconds"), notes=item.get("notes"),
                ))
    return block


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


def _factory_page_context() -> tuple[list[Athlete], list[Exercise]]:
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
    return athletes, accessory_exercises


def _validation_field(message: str) -> str | None:
    lowered = message.casefold()
    if "override reason" in lowered:
        return "override_reason"
    if "squat frequency" in lowered:
        return "squat_frequency"
    if "bench frequency" in lowered:
        return "bench_frequency"
    if "deadlift frequency" in lowered:
        return "deadlift_frequency"
    if "training days" in lowered or "every training day" in lowered:
        return "training_days"
    if "accessor" in lowered:
        return "accessory_exercise_id"
    if "date" in lowered:
        return "meet_date"
    return None


def _request_contract_error() -> tuple[str, str] | None:
    integer_fields = {
        "athlete_id": (1, None, "Choose an athlete."),
        "week_count": (1, 24, "Weeks must be between 1 and 24."),
        "training_days": (1, 7, "Training days must be between 1 and 7."),
        "squat_frequency": (0, 5, "Squat frequency must be between 0 and 5."),
        "bench_frequency": (0, 7, "Bench frequency must be between 0 and 7."),
        "deadlift_frequency": (0, 2, "Deadlift frequency must be between 0 and 2."),
    }
    for field, (minimum, maximum, message) in integer_fields.items():
        raw = request.form.get(field)
        if field != "athlete_id" and raw in (None, ""):
            continue
        try:
            value = int(raw or "")
        except ValueError:
            return field, message
        if value < minimum or (maximum is not None and value > maximum):
            return field, message
    for raw in request.form.getlist("accessory_exercise_id"):
        try:
            int(raw)
        except ValueError:
            return "accessory_exercise_id", "Choose an available accessory exercise."
    return None


def _render_factory_validation(
    message: str,
    *,
    field: str | None = None,
    athlete: Athlete | None = None,
    proposal: AthleteStateRecommendation | None = None,
    status: int = 422,
):
    athletes, accessory_exercises = _factory_page_context()
    field = field or _validation_field(message)
    errors = {field: message} if field else {"form": message}
    context: dict[str, Any] = {
        "athletes": athletes,
        "accessory_exercises": accessory_exercises,
        "form": request.form,
        "selected_athlete": athlete,
        "preview": None,
        "errors": errors,
        "golden_programmes": golden_programmes(),
    }
    if proposal is not None:
        payload = proposal.recommendation_json
        previous_factory = _factory_from_payload(payload)
        previous_athlete = db.session.get(Athlete, proposal.athlete_id)
        previous_preview = payload["preview"]
        previous_intelligence = WeeklyProgrammingIntelligence().preview(
            previous_factory, previous_athlete, previous_preview
        )
        context.update(
            preview=previous_preview,
            intelligence=previous_intelligence,
            explanation=_proposal_explanation(
                previous_factory, previous_preview, previous_intelligence
            ),
            selected_athlete=previous_athlete,
            proposal=proposal,
            proposal_integrity=_proposal_integrity(payload),
            preview_stale=True,
        )
    return render_template("programming/factory.html", **context), status


@block_factory_bp.get("/programming/factory")
def wizard():
    selected_athlete_id = request.args.get("athlete_id", type=int)
    selected_athlete = (
        require_athlete_access(selected_athlete_id)
        if selected_athlete_id is not None
        else None
    )
    athletes, accessory_exercises = _factory_page_context()

    return render_template(
        "programming/factory.html",
        athletes=athletes,
        preview=None,
        form={},
        selected_athlete=selected_athlete,
        accessory_exercises=accessory_exercises,
        golden_programmes=golden_programmes(),
    )


@block_factory_bp.post("/programming/factory/preview")
def preview():
    contract_error = _request_contract_error()
    if contract_error:
        field, message = contract_error
        return _render_factory_validation(message, field=field)
    try:
        factory = _parse_factory_request()
    except ValueError:
        return _render_factory_validation(
            "Enter a valid date and whole numbers for the factory fields."
        )
    athlete = require_athlete_access(factory.athlete_id)
    factory = _apply_active_coach_overrides(factory)

    athletes, accessory_exercises = _factory_page_context()

    try:
        scheduled_preview = _preview(factory)
        intelligence_preview = WeeklyProgrammingIntelligence().preview(
            factory, athlete, scheduled_preview
        )
    except ValueError as error:
        return _render_factory_validation(str(error), athlete=athlete)

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
            return _render_factory_validation(
                "Editing a generated proposal requires a coach override reason.",
                athlete=athlete,
                proposal=previous,
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
        golden_programmes=golden_programmes(),
    )


@block_factory_bp.post("/programming/factory")
def generate():
    proposal, payload = _load_proposal()
    if proposal.generator_version != PROPOSAL_VERSION:
        abort(409, description="Proposal must be previewed with the current version.")
    athlete = require_athlete_access(proposal.athlete_id)
    try:
        if payload.get("source_token") != _proposal_source_token(proposal.athlete_id):
            abort(409, description="Proposal is stale because its source data changed; preview again.")
        graph = _validate_programme_graph(payload.get("programme"))
        block = _materialize_programme_graph(graph, athlete)
        append_revision(block, change_type="factory_programme_created", summary="Created programme from accepted factory proposal", reason=proposal.rationale)
        if not _mark_decided(proposal, "accepted"):
            abort(409, description="Proposal was already decided and cannot be replayed.")
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        abort(409, description=f"Proposal materialization failed: {error}")
    except Exception:
        db.session.rollback()
        raise

    return redirect(url_for("programming.block", block_id=block.id))


@block_factory_bp.post("/programming/factory/proposal/dismiss")
def dismiss_proposal():
    proposal, _payload = _load_proposal()
    if not _mark_decided(proposal, "dismissed"):
        abort(409, description="Proposal was already decided and cannot be replayed.")
    db.session.commit()
    return redirect(url_for("block_factory.wizard", athlete_id=proposal.athlete_id))
