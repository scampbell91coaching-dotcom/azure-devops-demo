"""Deterministic, read-only coaching decisions from recorded training outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models.athlete import Athlete
from ..models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from .competition_bodyweight import BodyweightPlanningContext, build_bodyweight_planning_context

CALCULATION_VERSION = "performance-decisions-v1"


@dataclass(frozen=True)
class MetricEvidence:
    key: str
    value: float | int | None
    unit: str
    explanation: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class LiftPerformance:
    lift: str
    volume_kg: float
    latest_e1rm_kg: float | None
    previous_e1rm_kg: float | None
    e1rm_change_percent: float | None
    top_set_e1rm_kg: float | None
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class CoachDecision:
    rule_id: str
    level: str
    title: str
    evidence: str
    action: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class PerformanceDecisionSummary:
    athlete_id: int
    block_id: int | None
    block_name: str | None
    window_start: date
    window_end: date
    calculation_version: str
    metrics: tuple[MetricEvidence, ...]
    lifts: tuple[LiftPerformance, ...]
    decisions: tuple[CoachDecision, ...]
    bodyweight_context: BodyweightPlanningContext
    limitations: tuple[str, ...]


def build_performance_decisions(
    athlete_id: int,
    *,
    as_of: date,
    block_id: int | None = None,
    window_days: int = 42,
) -> PerformanceDecisionSummary | None:
    """Return explainable decisions scoped to one athlete and optional block."""
    if window_days < 1:
        raise ValueError("window_days must be at least 1")
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        return None

    block = None
    if block_id is not None:
        block = TrainingBlock.query.filter_by(id=block_id, athlete_id=athlete_id).first()
        if block is None:
            return None

    start = as_of - timedelta(days=window_days - 1)
    start_at = datetime.combine(start, datetime.min.time())
    end_at = datetime.combine(as_of + timedelta(days=1), datetime.min.time())
    query = (
        TrainingSetResult.query.options(
            joinedload(TrainingSetResult.session_log),
            joinedload(TrainingSetResult.prescription).joinedload(ExercisePrescription.lift_slot),
        )
        .join(TrainingSessionLog)
        .filter(
            TrainingSessionLog.athlete_id == athlete_id,
            TrainingSessionLog.status == "completed",
            TrainingSessionLog.completed_at >= start_at,
            TrainingSessionLog.completed_at < end_at,
        )
    )
    if block is not None:
        query = (query.join(TrainingSession, TrainingSessionLog.session_id == TrainingSession.id)
                 .join(TrainingWeek).filter(TrainingWeek.block_id == block.id))
    rows = query.order_by(TrainingSessionLog.completed_at.asc(), TrainingSetResult.id.asc()).all()

    decided = [row for row in rows if row.completed or row.skipped]
    completed = [row for row in decided if row.completed]
    comparable_rpe = [row for row in completed if row.prescribed_rpe is not None and row.actual_rpe is not None]
    exact_rep_rows = [(row, _exact_reps(row.prescribed_reps)) for row in decided]
    exact_rep_rows = [(row, reps) for row, reps in exact_rep_rows if reps is not None]
    completed_reps = sum(row.actual_reps or 0 for row, _ in exact_rep_rows if row.completed)
    missed_reps = sum(reps if row.skipped else max(reps - (row.actual_reps or 0), 0)
                      for row, reps in exact_rep_rows)

    metrics: list[MetricEvidence] = []
    if decided:
        refs = _refs(decided)
        metrics.append(MetricEvidence("set_completion_rate", round(len(completed) / len(decided), 4), "rate",
            f"{len(completed)} completed of {len(decided)} sets marked completed or skipped.", refs))
    if comparable_rpe:
        within = sum(abs(row.actual_rpe - row.prescribed_rpe) <= .5 for row in comparable_rpe)
        mean_delta = sum(row.actual_rpe - row.prescribed_rpe for row in comparable_rpe) / len(comparable_rpe)
        refs = _refs(comparable_rpe, ":actual_rpe,prescribed_rpe")
        metrics.extend((
            MetricEvidence("rpe_adherence_rate", round(within / len(comparable_rpe), 4), "rate",
                f"{within} of {len(comparable_rpe)} completed sets were within ±0.5 RPE.", refs),
            MetricEvidence("mean_rpe_delta", round(mean_delta, 2), "RPE",
                "Mean actual RPE minus prescribed RPE; positive means training felt harder than prescribed.", refs),
        ))
    if exact_rep_rows:
        refs = _refs(row for row, _ in exact_rep_rows)
        metrics.extend((
            MetricEvidence("completed_reps", completed_reps, "reps", "Actual reps from rows with an exact integer prescription.", refs),
            MetricEvidence("missed_reps", missed_reps, "reps", "Skipped prescribed reps plus shortfalls against exact integer prescriptions.", refs),
        ))

    lifts = tuple(_lift_performance(family, rows) for family in ("squat", "bench", "deadlift"))
    bodyweight = build_bodyweight_planning_context(athlete, as_of=as_of)
    decisions = _decisions(metrics, lifts, bodyweight)
    limitations: list[str] = []
    if not rows:
        limitations.append("No completed set results were recorded in this window.")
    if rows and not comparable_rpe:
        limitations.append("RPE adherence is unavailable because no completed set has both prescribed and actual RPE.")
    if rows and not exact_rep_rows:
        limitations.append("Rep completion is unavailable because prescriptions are missing or use non-exact rep ranges.")
    unsupported = sum(1 for row in completed if _lift_family(row) is None)
    if unsupported:
        limitations.append(f"{unsupported} completed sets lack persisted SBD lift-family provenance and are excluded from SBD metrics.")

    return PerformanceDecisionSummary(
        athlete.id, block.id if block else None, block.name if block else None,
        start, as_of, CALCULATION_VERSION, tuple(metrics), lifts, decisions,
        bodyweight, tuple(limitations),
    )


def _lift_performance(family: str, rows: list[TrainingSetResult]) -> LiftPerformance:
    applicable = [row for row in rows if row.completed and _lift_family(row) == family]
    valid = [row for row in applicable if row.actual_load_kg is not None and row.actual_reps is not None]
    volume = sum(row.actual_load_kg * row.actual_reps for row in valid)
    estimates = [(row, _e1rm(row)) for row in valid if _e1rm(row) is not None]
    latest = estimates[-1][1] if estimates else None
    previous = estimates[-2][1] if len(estimates) > 1 else None
    change = round((latest - previous) / previous * 100, 1) if latest is not None and previous else None
    top = [(row, estimate) for row, estimate in estimates
           if row.prescription is not None and row.prescription.slot_role == "top_set"]
    return LiftPerformance(
        family, round(volume, 1), latest, previous, change,
        top[-1][1] if top else None, _refs(applicable),
    )


def _decisions(metrics: list[MetricEvidence], lifts: tuple[LiftPerformance, ...],
               bodyweight: BodyweightPlanningContext) -> tuple[CoachDecision, ...]:
    by_key = {metric.key: metric for metric in metrics}
    decisions: list[CoachDecision] = []
    completion = by_key.get("set_completion_rate")
    adherence = by_key.get("rpe_adherence_rate")
    delta = by_key.get("mean_rpe_delta")
    if completion and completion.value is not None and completion.value < .85:
        decisions.append(CoachDecision("completion-below-85", "review", "Review training completion",
            f"Set completion was {completion.value:.0%}; threshold is 85%.",
            "Review missed work and its recorded notes before adding load or volume.", completion.source_refs))
    if adherence and adherence.value is not None and adherence.value < .70:
        direction = "above" if delta and delta.value and delta.value > 0 else "below" if delta and delta.value and delta.value < 0 else "away from"
        decisions.append(CoachDecision("rpe-adherence-below-70", "review", "Calibrate the prescription",
            f"RPE adherence was {adherence.value:.0%}; mean actual RPE was {direction} prescription by {abs(delta.value):.2f} RPE." if delta and delta.value is not None else f"RPE adherence was {adherence.value:.0%}.",
            "Review load selection and athlete RPE calibration before progressing the next exposure.", adherence.source_refs))
    declining = [lift for lift in lifts if lift.e1rm_change_percent is not None and lift.e1rm_change_percent <= -3]
    for lift in declining:
        decisions.append(CoachDecision(f"{lift.lift}-e1rm-down-3", "review", f"Review {lift.lift} performance",
            f"Latest Epley e1RM is {lift.latest_e1rm_kg:.1f} kg, {abs(lift.e1rm_change_percent):.1f}% below the prior eligible set.",
            "Check set execution, fatigue and prescription context before the next load increase.", lift.source_refs[-2:]))
    days = bodyweight.competition.days_away
    if days is not None and 0 <= days <= 28 and (bodyweight.latest is None or not bodyweight.weight_class):
        refs = tuple(ref for ref in (bodyweight.competition.source_ref,
                                     bodyweight.latest.source_ref if bodyweight.latest else None) if ref)
        decisions.append(CoachDecision("meet-context-incomplete-28-days", "priority", "Complete meet weight context",
            f"Meet is {days} days away; current bodyweight or weight class is missing.",
            "Record current bodyweight and confirm weight class before making weight-management decisions.", refs))
    if not decisions:
        refs = tuple(ref for metric in metrics for ref in metric.source_refs)
        if refs:
            decisions.append(CoachDecision("no-threshold-triggered", "maintain", "Maintain and monitor",
                "Recorded completion, RPE and e1RM comparisons did not cross a review threshold.",
                "Keep the current prescription and reassess when more completed exposures are recorded.", refs))
    return tuple(decisions)


def _lift_family(row: TrainingSetResult) -> str | None:
    prescription = row.prescription
    return prescription.lift_slot.lift_family if prescription and prescription.lift_slot else None


def _e1rm(row: TrainingSetResult) -> float | None:
    if row.actual_load_kg is None or row.actual_reps is None or not 1 <= row.actual_reps <= 12:
        return None
    return round(row.actual_load_kg * (1 + row.actual_reps / 30), 1)


def _exact_reps(value: str | None) -> int | None:
    if value is None or not value.strip().isdigit():
        return None
    parsed = int(value)
    return parsed if parsed >= 0 else None


def _refs(rows: Iterable[TrainingSetResult], suffix: str = "") -> tuple[str, ...]:
    return tuple(f"training_set_result:{row.id}{suffix}" for row in rows)
