from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import mean

from sqlalchemy.orm import selectinload

from ..models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)


LIFTS = ("squat", "bench", "deadlift")


@dataclass(frozen=True)
class PerformancePoint:
    recorded_on: date
    value: float


@dataclass(frozen=True)
class LiftTrend:
    lift: str
    points: tuple[PerformancePoint, ...]


@dataclass(frozen=True)
class CoachDecision:
    status: str
    headline: str
    explanation: str


@dataclass(frozen=True)
class CoachAthletePerformance:
    blocks: tuple[TrainingBlock, ...]
    selected_block: TrainingBlock | None
    session_count: int
    set_count: int
    completed_reps: int
    missed_reps: int | None
    volume_kg: float | None
    average_prescribed_rpe: float | None
    average_actual_rpe: float | None
    rpe_adherence_percent: int | None
    top_set_count: int
    e1rm_trends: tuple[LiftTrend, ...]
    volume_trend: tuple[PerformancePoint, ...]
    decision: CoachDecision


def get_coach_athlete_performance(
    athlete_id: int, *, block_id: int | None = None
) -> CoachAthletePerformance:
    """Build explainable performance metrics for one explicitly scoped athlete."""
    blocks = tuple(
        TrainingBlock.query.filter_by(athlete_id=athlete_id)
        .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
        .all()
    )
    selected = next((block for block in blocks if block.id == block_id), None)
    if block_id is not None and selected is None:
        raise LookupError("Training block does not belong to this athlete")

    query = (
        TrainingSessionLog.query.options(
            selectinload(TrainingSessionLog.results)
            .selectinload(TrainingSetResult.prescription)
            .selectinload(ExercisePrescription.lift_slot),
            selectinload(TrainingSessionLog.session)
            .selectinload(TrainingSession.week)
            .selectinload(TrainingWeek.block),
        )
        .filter_by(athlete_id=athlete_id, status="completed")
        .order_by(TrainingSessionLog.completed_at.asc(), TrainingSessionLog.id.asc())
    )
    logs = query.all()
    if selected is not None:
        logs = [
            log
            for log in logs
            if log.session is not None and log.session.week.block_id == selected.id
        ]

    results = [result for log in logs for result in log.results]
    completed = [result for result in results if result.completed and not result.skipped]
    completed_reps = sum(result.actual_reps or 0 for result in completed)

    rep_pairs = [
        (prescribed, result.actual_reps or 0)
        for result in results
        if not result.is_extra
        and (prescribed := _exact_reps(result.prescribed_reps)) is not None
    ]
    missed_reps = (
        sum(max(prescribed - actual, 0) for prescribed, actual in rep_pairs)
        if rep_pairs
        else None
    )

    rpe_pairs = [
        (result.prescribed_rpe, result.actual_rpe)
        for result in completed
        if result.prescribed_rpe is not None and result.actual_rpe is not None
    ]
    sbd_results = [result for result in completed if _lift_family(result) is not None]
    volume = sum(
        result.actual_load_kg * result.actual_reps
        for result in sbd_results
        if result.actual_load_kg is not None and result.actual_reps is not None
    )
    volume_has_data = any(
        result.actual_load_kg is not None and result.actual_reps is not None
        for result in sbd_results
    )

    e1rm: dict[str, list[PerformancePoint]] = {lift: [] for lift in LIFTS}
    daily_volume: dict[date, float] = {}
    top_sets = 0
    for log in logs:
        if log.completed_at is None:
            continue
        day = log.completed_at.date()
        daily_best: dict[str, float] = {}
        for result in log.results:
            lift = _lift_family(result)
            if not result.completed or result.skipped or lift is None:
                continue
            if result.prescription and result.prescription.slot_role == "top_set":
                top_sets += 1
            if result.actual_load_kg is not None and result.actual_reps:
                estimate = result.actual_load_kg * (1 + result.actual_reps / 30)
                daily_best[lift] = max(daily_best.get(lift, 0), estimate)
                daily_volume[day] = daily_volume.get(day, 0) + (
                    result.actual_load_kg * result.actual_reps
                )
        for lift, value in daily_best.items():
            e1rm[lift].append(PerformancePoint(day, round(value, 1)))

    adherence = (
        round(
            100
            * sum(
                abs(actual - prescribed) <= 0.5
                for prescribed, actual in rpe_pairs
            )
            / len(rpe_pairs)
        )
        if rpe_pairs
        else None
    )
    avg_delta = (
        mean(actual - prescribed for prescribed, actual in rpe_pairs)
        if rpe_pairs
        else None
    )
    decision = _decision(len(logs), missed_reps, adherence, avg_delta)
    return CoachAthletePerformance(
        blocks=blocks,
        selected_block=selected,
        session_count=len(logs),
        set_count=len(completed),
        completed_reps=completed_reps,
        missed_reps=missed_reps,
        volume_kg=round(volume, 1) if volume_has_data else None,
        average_prescribed_rpe=(
            round(mean(pair[0] for pair in rpe_pairs), 1) if rpe_pairs else None
        ),
        average_actual_rpe=(
            round(mean(pair[1] for pair in rpe_pairs), 1) if rpe_pairs else None
        ),
        rpe_adherence_percent=adherence,
        top_set_count=top_sets,
        e1rm_trends=tuple(LiftTrend(lift, tuple(e1rm[lift])) for lift in LIFTS),
        volume_trend=tuple(
            PerformancePoint(day, round(value, 1))
            for day, value in sorted(daily_volume.items())
        ),
        decision=decision,
    )


def _exact_reps(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    return int(stripped) if stripped.isdigit() else None


def _lift_family(result: TrainingSetResult) -> str | None:
    if result.prescription and result.prescription.lift_slot:
        return result.prescription.lift_slot.lift_family
    name = result.exercise_name.lower()
    return next((lift for lift in LIFTS if lift in name), None)


def _decision(
    session_count: int,
    missed_reps: int | None,
    adherence: int | None,
    average_rpe_delta: float | None,
) -> CoachDecision:
    if session_count == 0:
        return CoachDecision(
            "insufficient",
            "No training decision yet",
            "No completed sessions exist in this view.",
        )
    if missed_reps is not None and missed_reps > 0:
        return CoachDecision(
            "review",
            "Review prescription before progressing",
            f"Athlete recorded {missed_reps} fewer reps than exact prescriptions.",
        )
    if average_rpe_delta is not None and average_rpe_delta >= 1:
        return CoachDecision(
            "review",
            "Hold progression and review fatigue",
            f"Actual RPE averaged {average_rpe_delta:.1f} above prescription.",
        )
    if adherence is not None and adherence >= 80:
        return CoachDecision(
            "positive",
            "Performance supports planned progression",
            f"{adherence}% of comparable sets were within 0.5 RPE of prescription "
            "with no recorded missed reps.",
        )
    if adherence is not None:
        return CoachDecision(
            "monitor",
            "Keep load stable and monitor",
            f"RPE adherence is {adherence}%; review the outlying sets before "
            "changing load.",
        )
    return CoachDecision(
        "insufficient",
        "More comparable data needed",
        "Completed training exists, but prescribed and actual RPE pairs are incomplete.",
    )
