"""Conservative, coach-controlled athlete adaptation policy.

The policy is deliberately separate from programme generation.  It explains
whether recorded evidence is strong enough to justify a change and describes
the smallest useful change; it never edits a programme.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


POLICY_VERSION = "athlete-adaptation-v1"


@dataclass(frozen=True)
class AdaptationEvidence:
    """One sourced observation.  ``period`` normally identifies a week."""

    signal: str
    value: float | bool | str
    period: str
    source_refs: tuple[str, ...] = ()
    lift_family: str | None = None
    explanation: str = ""


@dataclass(frozen=True)
class AdaptationAdjustment:
    kind: str
    amount: float | int | None
    lift_family: str | None
    preserves_frequency: bool = True
    preserves_exercise: bool = True


@dataclass(frozen=True)
class AdaptationRecommendation:
    decision: str
    adjustment: AdaptationAdjustment | None
    rationale: tuple[str, ...]
    confidence: str
    evidence: tuple[AdaptationEvidence, ...]
    conflicts: tuple[str, ...]
    coach_acknowledgement_required: bool
    policy_version: str = POLICY_VERSION

    def as_payload(self) -> dict[str, Any]:
        adjustment = None
        if self.adjustment:
            adjustment = {
                "kind": self.adjustment.kind,
                "amount": self.adjustment.amount,
                "lift_family": self.adjustment.lift_family,
                "preserves_frequency": self.adjustment.preserves_frequency,
                "preserves_exercise": self.adjustment.preserves_exercise,
            }
        return {
            "schema_version": 1,
            "policy_version": self.policy_version,
            "decision": self.decision,
            "adjustment": adjustment,
            "rationale": list(self.rationale),
            "confidence": self.confidence,
            "conflicts": list(self.conflicts),
            "coach_acknowledgement_required": self.coach_acknowledgement_required,
            "evidence": [
                {
                    "signal": row.signal, "value": row.value,
                    "period": row.period, "source_refs": list(row.source_refs),
                    "lift_family": row.lift_family,
                    "explanation": row.explanation,
                }
                for row in self.evidence
            ],
        }


class ConservativeAdaptationPolicy:
    """Choose the first-line intervention supported by repeated evidence.

    Values use intentionally simple recorded contracts: RPE drift is actual
    minus prescribed, soreness/pain are 0--10, and rates are 0--1.  Unknown
    signals remain visible as evidence but cannot trigger an intervention.
    """

    REPEATED_PERIODS = 2

    def evaluate(
        self, evidence: Iterable[AdaptationEvidence]
    ) -> AdaptationRecommendation:
        rows = tuple(evidence)
        conflicts = self._conflicts(rows)
        pain = self._meaningful_pain(rows)
        soreness = self._persistent(rows, "soreness", lambda value: value >= 7)
        overshoot = self._persistent(rows, "rpe_drift", lambda value: value >= 1)
        undershoot = self._persistent(rows, "rpe_drift", lambda value: value <= -1)
        missed = self._persistent(rows, "completion_rate", lambda value: value < .85)
        failure = self._failure_to_adapt(rows)

        # Pain is the sole early-intervention signal.  A more stable movement is
        # still a proposal, not a medical conclusion or automatic substitution.
        if pain:
            return self._recommend(
                rows, conflicts, "increase_stability", None, pain[0].lift_family,
                ("Meaningful recorded pain increase warrants review before waiting for a block-level trend.",
                 "Preserve the schedule and exposure frequency while considering a more stable exercise."),
                "high" if len(pain) > 1 else "moderate", preserves_exercise=False,
            )
        if soreness or missed or failure:
            reason = (
                "Difficult soreness persisted across multiple periods."
                if soreness else
                "Missed work persisted across multiple periods."
                if missed else
                "Performance failed to adapt across the observed block trend."
            )
            family = self._common_family(soreness or missed or failure)
            return self._recommend(
                rows, conflicts, "reduce_sets", 1, family,
                (reason, "Reduce dose by one set before changing frequency, exercise, or weekly structure."),
                "high" if len({r.period for r in soreness or missed or failure}) >= 3 else "moderate",
            )
        if overshoot:
            return self._recommend(
                rows, conflicts, "lower_rpe", .5, self._common_family(overshoot),
                ("Actual RPE persistently exceeded prescription across multiple periods.",
                 "Lower target RPE by 0.5 while preserving sets, exercise, frequency, and weekly structure."),
                "high" if len({r.period for r in overshoot}) >= 3 else "moderate",
            )
        if undershoot:
            return AdaptationRecommendation(
                "maintain", None,
                ("RPE undershoot is tracked, but conservative policy does not automatically add work.",),
                "moderate", rows, conflicts, False,
            )
        return AdaptationRecommendation(
            "maintain", None,
            ("Evidence has not crossed a conservative intervention threshold; maintain the current block and observe the trend.",),
            "low" if not rows else "moderate", rows, conflicts, False,
        )

    def _recommend(
        self, rows: tuple[AdaptationEvidence, ...], conflicts: tuple[str, ...],
        kind: str, amount: float | int | None, family: str | None,
        rationale: tuple[str, ...], confidence: str, *, preserves_exercise: bool = True,
    ) -> AdaptationRecommendation:
        return AdaptationRecommendation(
            "recommend", AdaptationAdjustment(
                kind, amount, family, preserves_frequency=True,
                preserves_exercise=preserves_exercise,
            ), rationale, confidence, rows, conflicts, True,
        )

    def _persistent(self, rows, signal, predicate):
        eligible = [r for r in rows if r.signal == signal and self._number(r.value) is not None
                    and predicate(self._number(r.value))]
        periods = {r.period for r in eligible}
        return eligible if len(periods) >= self.REPEATED_PERIODS else []

    def _meaningful_pain(self, rows):
        direct = [r for r in rows if r.signal == "pain_increase"
                  and self._number(r.value) is not None and self._number(r.value) >= 2]
        by_family: dict[str | None, list[AdaptationEvidence]] = {}
        for row in rows:
            if row.signal == "pain" and self._number(row.value) is not None:
                by_family.setdefault(row.lift_family, []).append(row)
        for family_rows in by_family.values():
            ordered = sorted(family_rows, key=lambda row: row.period)
            if len(ordered) > 1 and self._number(ordered[-1].value) - self._number(ordered[-2].value) >= 2:
                direct.append(ordered[-1])
        return direct

    def _failure_to_adapt(self, rows):
        declines = self._persistent(rows, "e1rm_change_percent", lambda value: value <= -3)
        reductions = self._persistent(rows, "top_set_change_percent", lambda value: value <= -5)
        volume_added = any(r.signal == "volume_change_percent" and
                           self._number(r.value) is not None and self._number(r.value) > 0 for r in rows)
        return reductions if reductions and volume_added else declines

    @staticmethod
    def _number(value):
        return None if isinstance(value, bool) or not isinstance(value, (int, float)) else float(value)

    @staticmethod
    def _common_family(rows: Sequence[AdaptationEvidence]) -> str | None:
        families = {row.lift_family for row in rows if row.lift_family}
        return next(iter(families)) if len(families) == 1 else None

    @staticmethod
    def _conflicts(rows: Sequence[AdaptationEvidence]) -> tuple[str, ...]:
        conflicts = []
        for signal in {row.signal for row in rows}:
            latest = [row for row in rows if row.signal == signal]
            if latest and all(isinstance(row.value, (int, float)) and not isinstance(row.value, bool) for row in latest):
                signs = {0 if row.value == 0 else 1 if row.value > 0 else -1 for row in latest}
                if 1 in signs and -1 in signs:
                    conflicts.append(f"Conflicting {signal} directions are present in the observation window.")
        return tuple(sorted(conflicts))


def apply_adjustment_to_graph(
    graph: Mapping[str, Any], adjustment: AdaptationAdjustment,
    *, stable_exercises: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a changed copy of a signed graph; never mutate the input graph."""
    import copy

    revised = copy.deepcopy(graph)
    for week in revised.get("weeks", []):
        for session in week.get("sessions", []):
            for item in session.get("prescriptions", []):
                slot = item.get("lift_slot") or {}
                if adjustment.lift_family and slot.get("lift_family") != adjustment.lift_family:
                    continue
                if adjustment.kind == "reduce_sets" and isinstance(item.get("sets"), int):
                    item["sets"] = max(1, item["sets"] - int(adjustment.amount or 1))
                elif adjustment.kind == "lower_rpe":
                    for field in ("rpe", "rpe_min", "rpe_max", "rpe_cap", "target_rpe"):
                        if isinstance(item.get(field), (int, float)) and not isinstance(item[field], bool):
                            item[field] = max(1, item[field] - float(adjustment.amount or .5))
                elif adjustment.kind == "increase_stability":
                    replacement = (stable_exercises or {}).get(item.get("exercise_name", ""))
                    if replacement:
                        item["exercise_name"] = replacement
                        item["exercise_id"] = None
    return revised


def create_adaptation_proposal(
    block: Any, recommendation: AdaptationRecommendation, *, rationale: str | None = None,
    stable_exercises: Mapping[str, str] | None = None,
) -> Any | None:
    """Persist a reviewable proposal without changing the accepted programme."""
    if recommendation.decision != "recommend" or recommendation.adjustment is None:
        return None
    from ..extensions import db
    from ..models.athlete_state import AthleteStateRecommendation

    source = programme_graph(block)
    revised = apply_adjustment_to_graph(
        source, recommendation.adjustment, stable_exercises=stable_exercises
    )
    payload = recommendation.as_payload()
    payload.update({
        "source_block_id": block.id,
        "source_revision_number": max((row.revision_number for row in block.revisions), default=0),
        "source_programme": source,
        "programme": revised,
    })
    proposal = AthleteStateRecommendation(
        athlete_id=block.athlete_id,
        recommendation_type="programming_adaptation_proposal_v1",
        recommendation_json=payload,
        rationale=rationale or " ".join(recommendation.rationale),
        signal_ids_json=sorted({ref for row in recommendation.evidence for ref in row.source_refs}),
        generator_version=POLICY_VERSION,
        status="proposed",
    )
    db.session.add(proposal)
    return proposal


def decide_adaptation(
    proposal: Any, *, action: str, decided_by: str,
    override_programme: Mapping[str, Any] | None = None,
    override_reason: str | None = None,
) -> Any | None:
    """Central decision boundary for accept, reject, preserve, and override.

    Acceptance materializes the already stored graph into a new draft block.
    It does not regenerate and never edits the source block or its revisions.
    """
    from datetime import UTC, datetime
    from ..extensions import db
    from ..models.athlete_state import AthleteStateOverride, AthleteStateRecommendation
    from ..programming_services.revisions import append_revision

    if proposal.recommendation_type != "programming_adaptation_proposal_v1":
        raise ValueError("Not an adaptation proposal")
    if proposal.status != "proposed":
        raise ValueError("Adaptation proposal was already decided")
    if action not in {"accept", "reject", "preserve", "override"}:
        raise ValueError("Unknown adaptation decision")
    if action in {"reject", "preserve"}:
        proposal.status = "dismissed"
        proposal.decided_at = datetime.now(UTC)
        proposal.decided_by = decided_by
        return None
    payload = proposal.recommendation_json
    if action == "override":
        if not override_reason or not override_reason.strip() or override_programme is None:
            raise ValueError("Coach override requires a reason and replacement programme")
        db.session.add(AthleteStateOverride(
            athlete_id=proposal.athlete_id, target_type="programming_proposal",
            target_ref=str(proposal.id), override_json={"replacement": override_programme},
            reason=override_reason.strip(), recorded_by=decided_by,
        ))
        proposal.status = "superseded"
        proposal.decided_at = datetime.now(UTC)
        proposal.decided_by = decided_by
        replacement_payload = {**payload, "programme": dict(override_programme),
                               "coach_override_reason": override_reason.strip()}
        replacement = AthleteStateRecommendation(
            athlete_id=proposal.athlete_id,
            recommendation_type=proposal.recommendation_type,
            recommendation_json=replacement_payload,
            rationale=override_reason.strip(), signal_ids_json=proposal.signal_ids_json,
            generator_version=proposal.generator_version, status="proposed",
        )
        db.session.add(replacement)
        return replacement

    block = materialize_programme_graph(payload["programme"], proposal.athlete_id)
    append_revision(
        block, change_type="athlete_state_adaptation",
        summary="Created programme revision from accepted adaptation proposal",
        reason=proposal.rationale,
    )
    proposal.status = "accepted"
    proposal.decided_at = datetime.now(UTC)
    proposal.decided_by = decided_by
    return block


def programme_graph(block: Any) -> dict[str, Any]:
    """Serialize all authored prescription semantics needed for exact cloning."""
    from ..programming_services.revisions import PRESCRIPTION_FIELDS

    return {
        "schema_version": 1,
        "block": {"name": f"{block.name} — adaptation", "objective": block.objective,
                  "status": "draft"},
        "weeks": [{
            "name": week.name, "position": week.position, "notes": week.notes,
            "sessions": [{
                "name": session.name, "day_label": session.day_label,
                "position": session.position, "notes": session.notes,
                "prescriptions": [{
                    **{field: getattr(item, field) for field in PRESCRIPTION_FIELDS
                       if field not in {"id", "lift_slot_id"}},
                    "lift_slot": ({
                        "position": item.lift_slot.position,
                        "lift_family": item.lift_slot.lift_family,
                        "exposure_role": item.lift_slot.exposure_role,
                    } if item.lift_slot else None),
                } for item in sorted(session.prescriptions, key=lambda row: (row.position, row.id or 0))],
            } for session in sorted(week.sessions, key=lambda row: (row.position, row.id or 0))],
        } for week in sorted(block.weeks, key=lambda row: (row.position, row.id or 0))],
    }


def materialize_programme_graph(graph: Mapping[str, Any], athlete_id: int) -> Any:
    """Copy the accepted proposal graph verbatim; no planner is invoked here."""
    from ..extensions import db
    from ..models.programming import (
        ExercisePrescription, ProgrammingLiftSlot, TrainingBlock,
        TrainingSession, TrainingWeek,
    )
    from ..programming_services.revisions import PRESCRIPTION_FIELDS

    block_data = graph["block"]
    block = TrainingBlock(
        athlete_id=athlete_id, name=block_data["name"],
        objective=block_data.get("objective"), status=block_data.get("status", "draft"),
    )
    db.session.add(block)
    for week_data in graph["weeks"]:
        week = TrainingWeek(
            block=block, name=week_data["name"], position=week_data["position"],
            notes=week_data.get("notes"),
        )
        db.session.add(week)
        for session_data in week_data["sessions"]:
            session = TrainingSession(
                week=week, name=session_data["name"], position=session_data["position"],
                day_label=session_data.get("day_label"), notes=session_data.get("notes"),
            )
            db.session.add(session)
            for item in session_data["prescriptions"]:
                slot_data = item.get("lift_slot")
                slot = ProgrammingLiftSlot(session=session, **slot_data) if slot_data else None
                if slot is not None:
                    db.session.add(slot)
                values = {field: item.get(field) for field in PRESCRIPTION_FIELDS
                          if field not in {"id", "lift_slot_id"}}
                prescription = ExercisePrescription(session=session, lift_slot=slot, **values)
                prescription.validate()
                db.session.add(prescription)
    return block
