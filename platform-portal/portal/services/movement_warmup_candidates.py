"""Explainable movement-need candidates for coach-selected warm-up protocols.

This module links existing deterministic coaching rules to existing, authored
protocol versions.  It never creates drills, diagnoses a cause, or assigns a
protocol without a separate coach action.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Protocol, Sequence

from ..models.programming import TrainingSession
from ..models.warmup import WarmupAssignment, WarmupProtocol
from .coaching_rules import evaluate_coaching_rules


MAPPING_VERSION = "movement-warmup-mapping-v1"


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
