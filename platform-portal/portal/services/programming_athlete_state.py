"""Deterministic translation of current athlete state for programming consumers."""
from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..models.athlete_state import (
    AthleteConstraintFlag, AthleteStateOverride, AthleteStateRecommendation,
    CoachTechnicalObservation,
)
from .athlete_state import calculate_signals

TRANSLATION_VERSION = "programming-athlete-state-v2"
OBSERVATION_WINDOW_DAYS = 28
IRRITATION_WINDOW_DAYS = 14
RECOMMENDATION_WINDOW_DAYS = 28


def aggregate_programming_athlete_state(
    athlete: Any, *, as_of: date | None = None
) -> dict[str, Any]:
    """Build a sourced advisory contract without diagnosing or writing state."""
    as_of = as_of or date.today()
    hard: list[dict[str, Any]] = []
    soft: list[dict[str, Any]] = []
    flags = AthleteConstraintFlag.query.filter(
        AthleteConstraintFlag.athlete_id == athlete.id,
        AthleteConstraintFlag.starts_on <= as_of,
        (AthleteConstraintFlag.resolved_on.is_(None))
        | (AthleteConstraintFlag.resolved_on > as_of),
    ).order_by(AthleteConstraintFlag.starts_on.asc(), AthleteConstraintFlag.id.asc())
    for flag in flags:
        if flag.flag_kind == "irritation" and flag.starts_on < as_of - timedelta(
            days=IRRITATION_WINDOW_DAYS - 1
        ):
            continue
        text = f"{flag.label} {flag.details or ''}"
        effects = _pain_effects(text) if flag.flag_kind == "irritation" else _constraint_effects(text)
        hard.append({
            "kind": flag.flag_kind,
            "label": flag.label,
            "effects": effects,
            "evidence": [{
                "reference": f"athlete_constraint_flag:{flag.id}",
                "reported_by": flag.reported_by,
                "starts_on": flag.starts_on.isoformat(),
                "source_ref": flag.source_ref,
            }],
            "explanation": (
                "Current reported irritation: avoid conflicting automatic choices and require coach review; this is not a diagnosis."
                if flag.flag_kind == "irritation"
                else "Explicit unresolved training constraint: apply as a hard filter until resolved."
            ),
        })

    window_start = as_of - timedelta(days=OBSERVATION_WINDOW_DAYS - 1)
    observations = CoachTechnicalObservation.query.filter(
        CoachTechnicalObservation.athlete_id == athlete.id,
        CoachTechnicalObservation.superseded_by_id.is_(None),
        CoachTechnicalObservation.observed_on >= window_start,
        CoachTechnicalObservation.observed_on <= as_of,
    ).order_by(CoachTechnicalObservation.observed_on.asc(), CoachTechnicalObservation.id.asc()).all()
    for item in observations:
        normalised = _normalise(item.observation)
        if "resolved" in normalised or normalised.startswith("no "):
            continue
        if "hip shift" in normalised and any(
            later.lift.casefold() == item.lift.casefold()
            and (later.observed_on, later.id) > (item.observed_on, item.id)
            and "hip shift" in _normalise(later.observation)
            and (
                _side(_normalise(later.observation)) is None
                or _side(normalised) is None
                or _side(_normalise(later.observation)) == _side(normalised)
            )
            and (
                "resolved" in _normalise(later.observation)
                or _normalise(later.observation).startswith("no ")
            )
            for later in observations
        ):
            continue
        effects: dict[str, Any] = {"lift_families": [item.lift.casefold()]}
        if "hip shift" in normalised:
            effects.update({
                "technical_signal": "hip_shift",
                "side": _side(normalised),
                "warmup_protocol_keys": ["squat-hip-shift-preparation"],
                "assistance_preference_tags": ["unilateral"],
            })
        soft.append({
            "kind": "technical_observation",
            "label": f"{item.lift}: {item.observation}",
            "effects": effects,
            "evidence": [{
                "reference": f"coach_technical_observation:{item.id}",
                "observed_on": item.observed_on.isoformat(),
                "recorded_by": item.recorded_by,
                "source_ref": item.source_ref,
            }],
            "explanation": "Recent coach observation for cueing and ranking; not a hard exclusion or diagnosis.",
        })

    recommendation_start = datetime.combine(
        as_of - timedelta(days=RECOMMENDATION_WINDOW_DAYS - 1), datetime.min.time()
    )
    recommendations = AthleteStateRecommendation.query.filter(
        AthleteStateRecommendation.athlete_id == athlete.id,
        ~AthleteStateRecommendation.recommendation_type.like("weekly_programming_%"),
        AthleteStateRecommendation.status.in_(("proposed", "accepted")),
        AthleteStateRecommendation.generated_at >= recommendation_start,
        AthleteStateRecommendation.generated_at < datetime.combine(
            as_of + timedelta(days=1), datetime.min.time()
        ),
    ).order_by(AthleteStateRecommendation.generated_at.asc(), AthleteStateRecommendation.id.asc())
    recommendation_items = [{
        "id": item.id, "type": item.recommendation_type, "status": item.status,
        "payload": item.recommendation_json,
        "evidence": [f"athlete_state_recommendation:{item.id}"],
    } for item in recommendations]

    now = datetime.now(UTC).replace(tzinfo=None)
    overrides = AthleteStateOverride.query.filter(
        AthleteStateOverride.athlete_id == athlete.id,
        AthleteStateOverride.target_type != "programming_proposal",
        AthleteStateOverride.revoked_at.is_(None),
        (AthleteStateOverride.expires_at.is_(None)) | (AthleteStateOverride.expires_at > now),
    ).order_by(AthleteStateOverride.recorded_at.asc(), AthleteStateOverride.id.asc())
    override_items = [{
        "id": item.id, "target_type": item.target_type, "target_ref": item.target_ref,
        "value": item.override_json, "reason": item.reason,
        "recorded_by": item.recorded_by,
        "evidence": [f"athlete_state_override:{item.id}"],
    } for item in overrides]

    readiness = [{
        "type": signal.signal_type, "value": signal.value,
        "evidence": list(signal.source_refs), "explanation": signal.explanation,
    } for signal in calculate_signals(athlete, as_of=as_of) if signal.signal_type in {
        "reported_fatigue", "reported_recovery", "reported_training_adherence",
        "logged_session_completion_rate", "set_completion_rate", "rpe_adherence_rate",
    }]
    excluded_tags = sorted({tag for item in hard for tag in item["effects"].get("excluded_constraint_tags", [])})
    review_reasons = _review_reasons(hard, soft)
    return {
        "version": TRANSLATION_VERSION, "athlete_id": athlete.id,
        "as_of": as_of.isoformat(), "hard_constraints": hard,
        "soft_signals": soft, "recommendations": recommendation_items,
        "coach_overrides": override_items, "readiness_signals": readiness,
        "consumer_hints": {
            "excluded_constraint_tags": excluded_tags,
            "affected_lift_families": sorted({
                lift for item in hard for lift in item["effects"].get("lift_families", [])
            }),
            "review_required": bool(review_reasons),
            "review_reasons": review_reasons,
        },
        "missing_data": not any((hard, soft, recommendation_items, override_items, readiness)),
        "medical_scope": "No diagnosis or treatment inference; coach review remains required.",
    }


def accessory_readiness_multiplier(programming_state: dict[str, Any]) -> float:
    """Translate Athlete State readiness evidence for accessory consumers."""
    multiplier = 1.0
    for signal in programming_state.get("readiness_signals", []):
        value = signal.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if signal.get("type") == "reported_fatigue" and value >= 8:
            multiplier = min(multiplier, .7)
        elif signal.get("type") == "reported_recovery" and value <= 3:
            multiplier = min(multiplier, .8)
    return multiplier


def _normalise(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _side(text: str) -> str | None:
    left = bool(re.search(r"(?:^| )left(?: |$)", text))
    right = bool(re.search(r"(?:^| )right(?: |$)", text))
    return "left" if left and not right else "right" if right and not left else None


def _pain_effects(text: str) -> dict[str, Any]:
    value = _normalise(text)
    tags: list[str] = []
    regions: list[str] = []
    lifts: list[str] = []
    if "shoulder" in value:
        regions.append("shoulder"); tags.extend(("shoulder_loading", "shoulder_irritation", "overhead_loading")); lifts.append("bench")
    if "elbow" in value:
        regions.append("elbow"); tags.extend(("elbow_loading", "elbow_irritation")); lifts.append("bench")
    if "hip" in value:
        regions.append("hip"); tags.extend(("hip_loading", "deep_hip_flexion")); lifts.extend(("squat", "deadlift"))
    if "low back" in value or "lower back" in value or "lumbar" in value:
        regions.append("low_back"); tags.extend(("axial_loading", "low_back_loading")); lifts.extend(("squat", "deadlift"))
    return {"affected_regions": regions, "lift_families": sorted(set(lifts)), "excluded_constraint_tags": sorted(set(tags))}


def _constraint_effects(text: str) -> dict[str, Any]:
    value = _normalise(text)
    lifts = [lift for lift in ("squat", "bench", "deadlift") if lift in value]
    pain = _pain_effects(text)
    return {
        "affected_regions": pain["affected_regions"],
        "lift_families": sorted(set(lifts + pain["lift_families"])),
        "excluded_constraint_tags": sorted(set(lifts + pain["excluded_constraint_tags"])),
    }


def _review_reasons(
    hard: list[dict[str, Any]], soft: list[dict[str, Any]]
) -> list[str]:
    """Return stable reasons when state cannot support a single safe choice."""
    reasons: list[str] = []
    for item in hard:
        if not item["effects"].get("affected_regions") and not item["effects"].get("lift_families"):
            reasons.append(f"Unmapped active constraint: {item['label']}")
    sided: dict[tuple[str, str], set[str]] = {}
    for item in soft:
        effects = item["effects"]
        side = effects.get("side")
        signal = effects.get("technical_signal")
        for lift in effects.get("lift_families", []):
            if signal and side:
                sided.setdefault((lift, signal), set()).add(side)
    for (lift, signal), sides in sorted(sided.items()):
        if len(sides) > 1:
            reasons.append(
                f"Conflicting recent {lift} {signal.replace('_', ' ')} observations: "
                + " and ".join(sorted(sides))
            )
    return reasons
