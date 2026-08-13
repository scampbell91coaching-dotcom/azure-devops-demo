"""Explicit athlete-state rules for deterministic assistance selection.

This module deliberately does not infer rules from observation, symptom, or
constraint text.  A state producer or coach must store the rule metadata; the
original records are referenced only as provenance.

The JSON contract requires ``rule_id``, ``effect``, ``candidate_tags``, and
``reason``. Soft effects also require an integer ``weight`` from 1 to 100.
Optional ``context`` keys are ``phases``, ``lift_families``, and
``session_tags``; every value is an exact-match list. Unknown or malformed
rules are ignored rather than guessed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from ..models.athlete_state import (
    AthleteStateOverride,
    AthleteStateRecommendation,
    AthleteStateSignal,
)


RULE_VERSION = "assistance-state-rules-v1"
RULE_SIGNAL_TYPE = "assistance_selection_rule"
RULE_RECOMMENDATION_TYPE = "assistance_selection_rule"
RULE_OVERRIDE_TARGET = "assistance_selection_rule"
EFFECTS = frozenset({"exclude", "penalty", "preference"})


@dataclass(frozen=True)
class AssistanceStateContext:
    athlete_id: int
    phase: str
    lift_families: frozenset[str]
    session_tags: frozenset[str] = frozenset()
    as_of: date | None = None


@dataclass(frozen=True)
class AssistanceStateRule:
    rule_id: str
    effect: str
    candidate_tags: frozenset[str]
    weight: int
    reason: str
    source_type: str
    source_id: int
    source_refs: tuple[str, ...]
    rule_version: str

    @property
    def provenance(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "effect": self.effect,
            "weight": self.weight,
            "source": f"{self.source_type}:{self.source_id}",
            "source_refs": list(self.source_refs),
            "reason": self.reason,
        }


def active_assistance_rules(context: AssistanceStateContext) -> tuple[AssistanceStateRule, ...]:
    """Load valid, explicitly stored rules applicable to this exact context."""
    evaluation_date = context.as_of or date.today()
    rules: list[AssistanceStateRule] = []

    signals = AthleteStateSignal.query.filter_by(
        athlete_id=context.athlete_id, signal_type=RULE_SIGNAL_TYPE
    ).order_by(AthleteStateSignal.calculated_at.asc(), AthleteStateSignal.id.asc())
    for row in signals:
        if row.window_start and evaluation_date < row.window_start:
            continue
        if row.window_end and evaluation_date > row.window_end:
            continue
        rule = _parse_rule(
            row.value_json,
            context,
            source_type="athlete_state_signal",
            source_id=row.id,
            source_refs=row.source_refs_json,
            default_version=row.calculation_version,
        )
        if rule is not None:
            rules.append(rule)

    recommendations = AthleteStateRecommendation.query.filter_by(
        athlete_id=context.athlete_id,
        recommendation_type=RULE_RECOMMENDATION_TYPE,
        status="accepted",
    ).order_by(
        AthleteStateRecommendation.generated_at.asc(),
        AthleteStateRecommendation.id.asc(),
    )
    for row in recommendations:
        rule = _parse_rule(
            row.recommendation_json,
            context,
            source_type="athlete_state_recommendation",
            source_id=row.id,
            source_refs=row.signal_ids_json,
            default_version=row.generator_version,
        )
        if rule is not None:
            rules.append(rule)

    now = datetime.now(UTC).replace(tzinfo=None)
    overrides = AthleteStateOverride.query.filter(
        AthleteStateOverride.athlete_id == context.athlete_id,
        AthleteStateOverride.target_type == RULE_OVERRIDE_TARGET,
        AthleteStateOverride.revoked_at.is_(None),
        (
            AthleteStateOverride.expires_at.is_(None)
            | (AthleteStateOverride.expires_at > now)
        ),
    ).order_by(AthleteStateOverride.recorded_at.asc(), AthleteStateOverride.id.asc())
    for row in overrides:
        payload = dict(row.override_json) if isinstance(row.override_json, dict) else {}
        payload.setdefault("rule_id", row.target_ref)
        payload.setdefault("reason", row.reason)
        rule = _parse_rule(
            payload,
            context,
            source_type="athlete_state_override",
            source_id=row.id,
            source_refs=(f"athlete_state_override:{row.id}",),
            default_version=RULE_VERSION,
        )
        if rule is not None:
            rules.append(rule)

    return tuple(sorted(rules, key=lambda item: (item.rule_id, item.source_type, item.source_id)))


def _parse_rule(
    payload: Any,
    context: AssistanceStateContext,
    *,
    source_type: str,
    source_id: int,
    source_refs: Any,
    default_version: str,
) -> AssistanceStateRule | None:
    if not isinstance(payload, dict):
        return None
    rule_id = _text(payload.get("rule_id"))
    effect = _text(payload.get("effect")).casefold()
    reason = _text(payload.get("reason"))
    candidate_tags = _string_set(payload.get("candidate_tags"))
    if not rule_id or effect not in EFFECTS or not reason or not candidate_tags:
        return None
    if not _matches_context(payload.get("context"), context):
        return None
    raw_weight = payload.get("weight", 0)
    if effect == "exclude":
        weight = 0
    elif isinstance(raw_weight, int) and not isinstance(raw_weight, bool) and 1 <= raw_weight <= 100:
        weight = raw_weight
    else:
        return None
    return AssistanceStateRule(
        rule_id=rule_id,
        effect=effect,
        candidate_tags=candidate_tags,
        weight=weight,
        reason=reason,
        source_type=source_type,
        source_id=source_id,
        source_refs=_source_refs(source_refs),
        rule_version=_text(payload.get("rule_version")) or default_version,
    )


def _matches_context(payload: Any, context: AssistanceStateContext) -> bool:
    if payload is None:
        return True
    if not isinstance(payload, dict):
        return False
    phases = _string_set(payload.get("phases"))
    lifts = _string_set(payload.get("lift_families"))
    session_tags = _string_set(payload.get("session_tags"))
    return (
        (not phases or context.phase.casefold() in phases or "all" in phases)
        and (not lifts or bool(context.lift_families.intersection(lifts)) or "all" in lifts)
        and (not session_tags or session_tags.issubset(context.session_tags))
    )


def _string_set(value: Any) -> frozenset[str]:
    if not isinstance(value, list):
        return frozenset()
    return frozenset(
        text.casefold() for item in value if (text := _text(item))
    )


def _source_refs(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for item in value if (text := _text(item)))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""
