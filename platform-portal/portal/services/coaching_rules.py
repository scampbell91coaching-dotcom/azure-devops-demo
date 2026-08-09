"""Deterministic, explainable coaching recommendation rules.

Rules only surface candidates for coach review.  They do not diagnose a
condition, prescribe treatment, or mutate programming.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..extensions import db
from ..models.athlete_state import (
    AthleteConstraintFlag,
    AthleteStateOverride,
    AthleteStateRecommendation,
    CoachTechnicalObservation,
)

GENERATOR_VERSION = "coaching-rules-v1"


@dataclass(frozen=True)
class ObservationRule:
    rule_id: str
    lift: str
    phrases: tuple[str, ...]
    contrary_phrases: tuple[str, ...]
    minimum_occurrences: int
    window_days: int
    priority: int
    confidence: str
    recommendation: str
    not_claiming: str


@dataclass(frozen=True)
class ConstraintRule:
    rule_id: str
    lift_families: tuple[str, ...]
    priority: int
    confidence: str
    recommendation_template: str
    not_claiming: str


# Explicit data definitions are intentionally small.  Adding a rule does not
# require changing evaluation control flow.
OBSERVATION_RULES = (
    ObservationRule(
        rule_id="technical.repeated_hip_shift.v1",
        lift="squat",
        phrases=("hip shift", "shifts at the hip"),
        contrary_phrases=("no hip shift", "hip shift resolved"),
        minimum_occurrences=2,
        window_days=28,
        priority=70,
        confidence="moderate",
        recommendation=(
            "Review the repeated squat hip-shift observations with the athlete "
            "and decide whether a coaching cue or programming adjustment is warranted."
        ),
        not_claiming=(
            "This does not identify an injury, diagnose a cause, or prescribe treatment."
        ),
    ),
    ObservationRule(
        rule_id="technical.repeated_heel_pressure.v1",
        lift="squat",
        phrases=("heel pressure", "heels lift", "heel lifts"),
        contrary_phrases=("heel pressure maintained", "heels stay down"),
        minimum_occurrences=2,
        window_days=28,
        priority=60,
        confidence="moderate",
        recommendation=(
            "Review the repeated heel-pressure observations and choose an "
            "appropriate coaching response for the next squat exposure."
        ),
        not_claiming=(
            "This does not diagnose mobility, pain, or injury, and it does not select an exercise."
        ),
    ),
)

CONSTRAINT_RULES = (
    ConstraintRule(
        rule_id="constraint.active_lift_family.v1",
        lift_families=("squat", "bench", "deadlift"),
        priority=90,
        confidence="high",
        recommendation_template=(
            "Review the active {lift_family} constraint before the next "
            "{lift_family} exposure; the coach decides whether programming changes."
        ),
        not_claiming=(
            "This records a reported training constraint; it is not a medical diagnosis "
            "or an exercise-suitability decision."
        ),
    ),
)


def evaluate_coaching_rules(
    athlete_id: int, *, as_of: date | None = None
) -> list[dict[str, Any]]:
    """Return stable, fully explained recommendation candidates."""
    as_of = as_of or date.today()
    candidates: list[dict[str, Any]] = []
    observations = CoachTechnicalObservation.query.filter_by(
        athlete_id=athlete_id, superseded_by_id=None
    ).order_by(
        CoachTechnicalObservation.observed_on.asc(),
        CoachTechnicalObservation.id.asc(),
    ).all()

    for rule in OBSERVATION_RULES:
        window_start = as_of - timedelta(days=rule.window_days - 1)
        relevant = [
            item
            for item in observations
            if item.lift.casefold() == rule.lift
            and window_start <= item.observed_on <= as_of
        ]
        contrary = [
            item
            for item in relevant
            if _contains_phrase(item.observation, rule.contrary_phrases)
        ]
        matched = [
            item
            for item in relevant
            if _contains_phrase(item.observation, rule.phrases)
            and item not in contrary
        ]
        # An explicit contrary observation makes the evidence ambiguous.  The
        # engine never guesses which coach observation should prevail.
        if len(matched) < rule.minimum_occurrences or contrary:
            continue
        candidates.append(
            _candidate(
                rule_id=rule.rule_id,
                priority=rule.priority,
                confidence=rule.confidence,
                recommendation=rule.recommendation,
                not_claiming=rule.not_claiming,
                matched_conditions=[
                    f"lift is {rule.lift}",
                    f"at least {rule.minimum_occurrences} matching observations "
                    f"in {rule.window_days} days",
                    "no contrary observation exists in the same window",
                ],
                sources=[_observation_source(item) for item in matched],
                as_of=as_of,
            )
        )

    flags = AthleteConstraintFlag.query.filter(
        AthleteConstraintFlag.athlete_id == athlete_id,
        AthleteConstraintFlag.resolved_on.is_(None),
        AthleteConstraintFlag.starts_on <= as_of,
    ).order_by(
        AthleteConstraintFlag.starts_on.asc(), AthleteConstraintFlag.id.asc()
    ).all()
    for rule in CONSTRAINT_RULES:
        for flag in flags:
            text = f"{flag.label} {flag.details or ''}"
            lift_family = next(
                (
                    family
                    for family in rule.lift_families
                    if _contains_phrase(text, (family,))
                ),
                None,
            )
            if lift_family is None:
                continue
            candidates.append(
                _candidate(
                    rule_id=f"{rule.rule_id}:{lift_family}",
                    priority=rule.priority,
                    confidence=rule.confidence,
                    recommendation=rule.recommendation_template.format(
                        lift_family=lift_family
                    ),
                    not_claiming=rule.not_claiming,
                    matched_conditions=[
                        "constraint is active on the evaluation date",
                        f"constraint explicitly names lift family {lift_family}",
                    ],
                    sources=[
                        {
                            "type": "constraint_flag",
                            "id": flag.id,
                            "reference": f"athlete_constraint_flag:{flag.id}",
                            "label": flag.label,
                            "flag_kind": flag.flag_kind,
                            "reported_by": flag.reported_by,
                            "starts_on": flag.starts_on.isoformat(),
                        }
                    ],
                    as_of=as_of,
                )
            )

    overrides = _active_rule_overrides(athlete_id)
    candidates = [
        _apply_override(item, overrides.get(item["rule_id"])) for item in candidates
    ]
    return sorted(
        candidates,
        key=lambda item: (-item["priority"], item["rule_id"], _source_key(item)),
    )


def persist_candidates(
    athlete_id: int, *, as_of: date | None = None
) -> list[AthleteStateRecommendation]:
    """Persist a reviewable snapshot without accepting or applying candidates."""
    records = []
    for candidate in evaluate_coaching_rules(athlete_id, as_of=as_of):
        record = AthleteStateRecommendation(
            athlete_id=athlete_id,
            recommendation_type="coaching_rule_candidate",
            recommendation_json=candidate,
            rationale="; ".join(candidate["matched_conditions"]),
            signal_ids_json=[
                source["reference"] for source in candidate["source_observations"]
            ],
            generator_version=GENERATOR_VERSION,
            status="proposed",
        )
        db.session.add(record)
        records.append(record)
    return records


def decide_candidate(
    recommendation: AthleteStateRecommendation,
    *,
    decision: str,
    decided_by: str,
    reason: str | None = None,
    replacement: str | None = None,
) -> AthleteStateRecommendation:
    """Record coach acceptance, rejection, or explained override."""
    if recommendation.recommendation_type != "coaching_rule_candidate":
        raise ValueError("Only coaching-rule candidates can be decided here")
    if recommendation.status != "proposed":
        raise ValueError("Candidate has already been decided")
    if decision not in {"accepted", "rejected", "overridden"}:
        raise ValueError("Decision must be accepted, rejected, or overridden")
    if decision in {"rejected", "overridden"} and not reason:
        raise ValueError("Rejected and overridden candidates require a reason")
    if decision == "overridden" and not replacement:
        raise ValueError("An overridden candidate requires replacement guidance")

    recommendation.status = "accepted" if decision == "accepted" else "dismissed"
    recommendation.decided_at = datetime.now(UTC)
    recommendation.decided_by = decided_by
    if decision == "overridden":
        rule_id = recommendation.recommendation_json["rule_id"]
        db.session.add(
            AthleteStateOverride(
                athlete_id=recommendation.athlete_id,
                target_type="coaching_rule",
                target_ref=rule_id,
                override_json={"recommendation": replacement},
                reason=reason,
                recorded_by=decided_by,
            )
        )
    elif decision == "rejected":
        payload = dict(recommendation.recommendation_json)
        payload["coach_decision"] = {"decision": "rejected", "reason": reason}
        recommendation.recommendation_json = payload
    return recommendation


def _candidate(**values: Any) -> dict[str, Any]:
    sources = values.pop("sources")
    as_of = values.get("as_of")
    if isinstance(as_of, date):
        values["as_of"] = as_of.isoformat()
    return {
        **values,
        "source_observations": sources,
        "generator_version": GENERATOR_VERSION,
        "coach_authority": "Candidate only; a coach must accept, reject, or override it.",
        "mutates_programming": False,
    }


def _observation_source(item: CoachTechnicalObservation) -> dict[str, Any]:
    return {
        "type": "technical_observation",
        "id": item.id,
        "reference": f"coach_technical_observation:{item.id}",
        "lift": item.lift,
        "observation": item.observation,
        "observed_on": item.observed_on.isoformat(),
        "source_ref": item.source_ref,
    }


def _contains_phrase(text: str, phrases: tuple[str, ...]) -> bool:
    normalised = " ".join(re.findall(r"[a-z0-9]+", text.casefold()))
    return any(
        re.search(
            rf"(?:^| ){re.escape(' '.join(phrase.casefold().split()))}(?: |$)",
            normalised,
        )
        for phrase in phrases
    )


def _active_rule_overrides(athlete_id: int) -> dict[str, AthleteStateOverride]:
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = AthleteStateOverride.query.filter(
        AthleteStateOverride.athlete_id == athlete_id,
        AthleteStateOverride.target_type == "coaching_rule",
        AthleteStateOverride.revoked_at.is_(None),
        (
            AthleteStateOverride.expires_at.is_(None)
            | (AthleteStateOverride.expires_at > now)
        ),
    ).order_by(
        AthleteStateOverride.recorded_at.asc(), AthleteStateOverride.id.asc()
    ).all()
    return {row.target_ref: row for row in rows}


def _apply_override(
    candidate: dict[str, Any], override: AthleteStateOverride | None
) -> dict[str, Any]:
    if override is None:
        return candidate
    result = dict(candidate)
    replacement = override.override_json.get("recommendation")
    if isinstance(replacement, str) and replacement.strip():
        result["recommendation"] = replacement.strip()
    result["coach_override"] = {
        "id": override.id,
        "reason": override.reason,
        "recorded_by": override.recorded_by,
        "replacement_applied": isinstance(replacement, str) and bool(replacement.strip()),
    }
    return result


def _source_key(candidate: dict[str, Any]) -> tuple[int, ...]:
    return tuple(source["id"] for source in candidate["source_observations"])
