"""Explainable movement-need candidates for coach-selected warm-up protocols.

This module links existing deterministic coaching rules to existing, authored
protocol versions.  It never creates drills, diagnoses a cause, or assigns a
protocol without a separate coach action.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol, Sequence

from ..models.athlete_state import (
    AthleteConstraintFlag,
    AthleteStateOverride,
    CoachTechnicalObservation,
)
from ..models.programming import TrainingSession
from ..models.warmup import WarmupAssignment, WarmupProtocol
from .coaching_rules import evaluate_coaching_rules


MAPPING_VERSION = "movement-warmup-mapping-v1"
RULE_LIBRARY_VERSION = "warmup-selection-rules-v1"


@dataclass(frozen=True)
class WarmupSelectionRule:
    """Coach-readable rule definition; matching contains no inferred anatomy."""

    rule_id: str
    source: str
    required_terms: tuple[tuple[str, ...], ...]
    lift_contexts: tuple[str, ...]
    block_intents: tuple[str, ...]
    protocol_keys: tuple[str, ...]
    action: str
    reason: str


# Each term group is OR; all groups must match. Protocol keys are authored-data
# contracts, so a missing protocol produces no proposal rather than an invented
# exercise. These are coaching observations and reported irritations, not
# diagnoses or claims about cause.
WARMUP_SELECTION_RULES = (
    WarmupSelectionRule(
        rule_id="warmup.observation.left_low_back_hip.v1",
        source="technical_observation",
        required_terms=(
            ("left", "left-sided", "left side"),
            ("low back", "low-back", "lower back"),
            ("hip",),
        ),
        lift_contexts=("squat", "deadlift"),
        block_intents=("generic", "strength", "technique", "hypertrophy"),
        protocol_keys=("wall-flamingo", "reverse-lunge"),
        action="consider",
        reason=(
            "Consider this coach-authored preparation option because the coach "
            "recorded a left-sided low-back/hip presentation in a relevant session context."
        ),
    ),
    WarmupSelectionRule(
        rule_id="warmup.constraint.elbow_irritation.v1",
        source="constraint_flag",
        required_terms=(("elbow",), ("irritation", "irritable", "sore", "discomfort")),
        lift_contexts=("bench",),
        block_intents=("generic", "strength", "technique", "hypertrophy", "peaking", "recovery"),
        protocol_keys=("bench-elbow-irritation-preparation",),
        action="consider",
        reason=(
            "Consider the coach-authored upper-body preparation option because an "
            "active elbow irritation was reported for a bench session."
        ),
    ),
)


@dataclass(frozen=True)
class MovementNeed:
    """Typed, non-diagnostic input seam for other candidate selectors."""

    lift_family: str
    rule_id: str
    rule_version: str
    source_ids: tuple[str, ...]
    reason: str


class AccessoryCandidateProvider(Protocol):
    """Optional seam; Block Factory is deliberately not coupled here."""

    def candidates_for(self, need: MovementNeed) -> Sequence[object]: ...


@dataclass(frozen=True)
class WarmupProtocolCandidate:
    protocol_id: int
    protocol_key: str
    protocol_version: int
    protocol_name: str
    lift_family: str
    rule_id: str
    rule_version: str
    mapping_version: str
    source_ids: tuple[str, ...]
    reason: str
    coach_override: dict | None = None
    action: str = "consider"
    evidence: tuple[str, ...] = ()
    block_intent: str = "generic"

    def assignment_reason(self) -> str:
        """Compact, persisted provenance for the existing 500-char field."""
        return json.dumps(
            {
                "candidate": "movement_warmup",
                "mapping": self.mapping_version,
                "rule": self.rule_id,
                "rule_version": self.rule_version,
                "protocol": self.protocol_key,
                "protocol_version": self.protocol_version,
                "sources": list(self.source_ids),
                "reason": self.reason,
                "action": self.action,
                "block_intent": self.block_intent,
            },
            separators=(",", ":"),
            sort_keys=True,
        )


# Protocol keys are an explicit coach-authored contract. A missing key produces
# no candidate: the engine does not invent a drill or select by fuzzy wording.
RULE_PROTOCOL_KEYS = {
    "technical.repeated_hip_shift.v1": ("squat", "squat-hip-shift-preparation"),
    "technical.repeated_heel_pressure.v1": (
        "squat",
        "squat-heel-pressure-preparation",
    ),
}
CONSTRAINT_PROTOCOL_KEYS = {
    "squat": "squat-constraint-preparation",
    "bench": "bench-constraint-preparation",
    "deadlift": "deadlift-constraint-preparation",
}


def movement_needs(athlete_id: int, *, as_of: date | None = None) -> tuple[MovementNeed, ...]:
    """Translate matched coaching rules into stable, typed movement needs."""
    rules = tuple(evaluate_coaching_rules(athlete_id, as_of=as_of))
    return _movement_needs_from_rules(rules)


def warmup_candidates(
    athlete_id: int,
    session: TrainingSession,
    *,
    as_of: date | None = None,
) -> tuple[WarmupProtocolCandidate, ...]:
    """Return deterministic protocol candidates relevant to this session."""
    session_lifts = {slot.lift_family for slot in session.lift_slots}
    assigned_ids = {
        row.protocol_id
        for row in WarmupAssignment.query.filter_by(
            athlete_id=athlete_id, session_id=session.id
        )
    }
    rules = {
        row["rule_id"]: row
        for row in evaluate_coaching_rules(athlete_id, as_of=as_of)
    }
    candidates = []
    for need in _movement_needs_from_rules(tuple(rules.values())):
        if need.lift_family not in session_lifts:
            continue
        mapped = RULE_PROTOCOL_KEYS.get(need.rule_id)
        protocol_key = mapped[1] if mapped is not None else CONSTRAINT_PROTOCOL_KEYS.get(
            need.lift_family
        )
        if protocol_key is None:
            continue
        protocol = (
            WarmupProtocol.query.filter_by(stable_key=protocol_key)
            .order_by(WarmupProtocol.version.desc(), WarmupProtocol.id.asc())
            .first()
        )
        if protocol is None or protocol.id in assigned_ids:
            continue
        rule = rules[need.rule_id]
        candidates.append(
            WarmupProtocolCandidate(
                protocol_id=protocol.id,
                protocol_key=protocol.stable_key,
                protocol_version=protocol.version,
                protocol_name=protocol.name,
                lift_family=need.lift_family,
                rule_id=need.rule_id,
                rule_version=need.rule_version,
                mapping_version=MAPPING_VERSION,
                source_ids=need.source_ids,
                reason=need.reason,
                coach_override=rule.get("coach_override"),
            )
        )
    candidates.extend(
        _contextual_candidates(
            athlete_id,
            session,
            assigned_ids=assigned_ids,
            as_of=as_of or date.today(),
        )
    )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.lift_family,
                item.rule_id,
                item.protocol_key,
                -item.protocol_version,
                item.source_ids,
            ),
        )
    )


def _contextual_candidates(
    athlete_id: int,
    session: TrainingSession,
    *,
    assigned_ids: set[int],
    as_of: date,
) -> list[WarmupProtocolCandidate]:
    """Evaluate the explicit athlete-state/session-context warm-up library."""
    session_lifts = {slot.lift_family for slot in session.lift_slots}
    block_intent = _block_intent(session.week.block.objective)
    observations = CoachTechnicalObservation.query.filter_by(
        athlete_id=athlete_id, superseded_by_id=None
    ).filter(
        CoachTechnicalObservation.observed_on >= as_of - timedelta(days=27),
        CoachTechnicalObservation.observed_on <= as_of,
    ).order_by(
        CoachTechnicalObservation.observed_on.asc(),
        CoachTechnicalObservation.id.asc(),
    ).all()
    flags = AthleteConstraintFlag.query.filter(
        AthleteConstraintFlag.athlete_id == athlete_id,
        AthleteConstraintFlag.starts_on <= as_of,
        AthleteConstraintFlag.resolved_on.is_(None),
    ).order_by(AthleteConstraintFlag.starts_on.asc(), AthleteConstraintFlag.id.asc()).all()
    overrides = _warmup_rule_overrides(athlete_id)
    result: list[WarmupProtocolCandidate] = []

    for rule in WARMUP_SELECTION_RULES:
        matching_lifts = sorted(session_lifts.intersection(rule.lift_contexts))
        if not matching_lifts or block_intent not in rule.block_intents:
            continue
        sources = []
        if rule.source == "technical_observation":
            sources = [
                (f"coach_technical_observation:{row.id}", row.observation)
                for row in observations
                if row.lift in rule.lift_contexts
                and _matches_terms(row.observation, rule.required_terms)
            ]
        elif rule.source == "constraint_flag":
            sources = [
                (f"athlete_constraint_flag:{row.id}", f"{row.label} {row.details or ''}".strip())
                for row in flags
                if _matches_terms(
                    f"{row.label} {row.details or ''} {row.flag_kind}",
                    rule.required_terms,
                )
            ]
        if not sources:
            continue
        override = overrides.get(rule.rule_id)
        if override is not None and override.override_json.get("action") == "remove":
            continue
        reason = rule.reason
        if override is not None:
            replacement = override.override_json.get("recommendation")
            if isinstance(replacement, str) and replacement.strip():
                reason = replacement.strip()
        for protocol_key in rule.protocol_keys:
            protocol = (
                WarmupProtocol.query.filter_by(stable_key=protocol_key)
                .order_by(WarmupProtocol.version.desc(), WarmupProtocol.id.asc())
                .first()
            )
            if protocol is None or protocol.id in assigned_ids:
                continue
            result.append(
                WarmupProtocolCandidate(
                    protocol_id=protocol.id,
                    protocol_key=protocol.stable_key,
                    protocol_version=protocol.version,
                    protocol_name=protocol.name,
                    lift_family=matching_lifts[0],
                    rule_id=rule.rule_id,
                    rule_version=RULE_LIBRARY_VERSION,
                    mapping_version=MAPPING_VERSION,
                    source_ids=tuple(source[0] for source in sources),
                    reason=reason,
                    coach_override=(
                        {"id": override.id, "reason": override.reason, "recorded_by": override.recorded_by}
                        if override is not None else None
                    ),
                    action=rule.action,
                    evidence=tuple(source[1] for source in sources),
                    block_intent=block_intent,
                )
            )
    return result


def _matches_terms(text: str, required_terms: tuple[tuple[str, ...], ...]) -> bool:
    normalised = " ".join(text.casefold().replace("-", " ").split())
    return all(any(term.replace("-", " ") in normalised for term in group) for group in required_terms)


def _block_intent(objective: str | None) -> str:
    text = (objective or "").casefold()
    categories = (
        ("peaking", ("peak", "competition", "taper")),
        ("recovery", ("recovery", "deload", "return to training")),
        ("technique", ("technique", "technical", "skill")),
        ("strength", ("strength", "intensity")),
        ("hypertrophy", ("hypertrophy", "muscle", "volume")),
    )
    return next((name for name, terms in categories if any(term in text for term in terms)), "generic")


def _warmup_rule_overrides(athlete_id: int) -> dict[str, AthleteStateOverride]:
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = AthleteStateOverride.query.filter(
        AthleteStateOverride.athlete_id == athlete_id,
        AthleteStateOverride.target_type == "warmup_selection_rule",
        AthleteStateOverride.revoked_at.is_(None),
        (
            AthleteStateOverride.expires_at.is_(None)
            | (AthleteStateOverride.expires_at > now)
        ),
    ).order_by(AthleteStateOverride.recorded_at.asc(), AthleteStateOverride.id.asc()).all()
    return {row.target_ref: row for row in rows}


def _movement_needs_from_rules(rules: tuple[dict, ...]) -> tuple[MovementNeed, ...]:
    needs = []
    for rule in rules:
        mapped = RULE_PROTOCOL_KEYS.get(rule["rule_id"])
        if mapped is not None:
            lift_family = mapped[0]
        elif rule["rule_id"].startswith("constraint.active_lift_family.v1:"):
            lift_family = rule["rule_id"].rsplit(":", 1)[1]
        else:
            continue
        needs.append(
            MovementNeed(
                lift_family=lift_family,
                rule_id=rule["rule_id"],
                rule_version=rule["generator_version"],
                source_ids=tuple(
                    source["reference"] for source in rule["source_observations"]
                ),
                reason=rule["recommendation"],
            )
        )
    return tuple(needs)


def find_candidate(
    athlete_id: int, session: TrainingSession, protocol_id: int
) -> WarmupProtocolCandidate | None:
    """Re-evaluate server-side so a submitted protocol ID cannot bypass a rule."""
    return next(
        (
            item
            for item in warmup_candidates(athlete_id, session)
            if item.protocol_id == protocol_id
        ),
        None,
    )
