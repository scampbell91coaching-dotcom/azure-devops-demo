"""Coach-facing execution analytics derived from persisted training logs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from ..models.programming import ExercisePrescription, TrainingSessionLog, TrainingSetResult

RPE_TOLERANCE = 0.5


@dataclass(frozen=True)
class RPEAdherence:
    comparable_sets: int
    adherent_sets: int
    above_sets: int
    below_sets: int
    unavailable_sets: int
    adherence_rate: float | None
    mean_variance: float | None


@dataclass(frozen=True)
class RepCompletion:
    decided_sets: int
    completed_sets: int
    skipped_sets: int
    completion_rate: float | None
    prescribed_reps: int
    completed_reps: int
    missed_reps: int
    unavailable_sets: int


@dataclass(frozen=True)
class TopSetPerformance:
    result_id: int
    performed_on: date
    exercise_name: str
    actual_load_kg: float | None
    actual_reps: int | None
    actual_rpe: float | None
    rpe_status: str | None


@dataclass(frozen=True)
class TrainingPerformanceSummary:
    rpe: RPEAdherence
    reps: RepCompletion
    top_sets: tuple[TopSetPerformance, ...]
    top_set_unavailable: int


def training_performance_summary(
    athlete_id: int,
    *,
    start: date,
    end: date,
    block_name: str | None = None,
) -> TrainingPerformanceSummary:
    """Summarise one athlete's logged work without imputing missing values.

    RPE targets use the existing prescription semantics: a single target allows
    +/- 0.5, a range uses its recorded bounds, and a cap is an upper bound.
    Prescription relationships are used only where the immutable result snapshot
    cannot represent a range/cap or top-set role; missing relationships are
    counted as unavailable rather than guessed.
    """
    if end < start:
        raise ValueError("end must be on or after start")

    query = (
        TrainingSetResult.query
        .join(TrainingSessionLog, TrainingSetResult.session_log_id == TrainingSessionLog.id)
        .outerjoin(ExercisePrescription, TrainingSetResult.prescription_id == ExercisePrescription.id)
        .filter(
            TrainingSessionLog.athlete_id == athlete_id,
            TrainingSessionLog.started_at >= datetime.combine(start, time.min),
            TrainingSessionLog.started_at < datetime.combine(end + timedelta(days=1), time.min),
        )
        .with_entities(TrainingSetResult, ExercisePrescription, TrainingSessionLog.started_at)
        .order_by(TrainingSessionLog.started_at.asc(), TrainingSetResult.id.asc())
    )
    if block_name is not None:
        query = query.filter(TrainingSessionLog.block_name == block_name)
    rows = query.all()

    comparable = adherent = above = below = rpe_unavailable = 0
    variances: list[float] = []
    decided = completed = skipped = 0
    prescribed_reps = completed_reps = missed_reps = rep_unavailable = 0
    top_sets: list[TopSetPerformance] = []
    top_unavailable = 0

    for result, prescription, started_at in rows:
        if result.completed or result.skipped:
            decided += 1
            completed += int(result.completed)
            skipped += int(result.skipped)
            if not result.is_extra:
                target_reps = _exact_reps(result.prescribed_reps)
                if target_reps is None:
                    rep_unavailable += 1
                else:
                    prescribed_reps += target_reps
                    actual = result.actual_reps if result.completed else 0
                    if actual is None:
                        rep_unavailable += 1
                    else:
                        completed_reps += actual
                        missed_reps += max(target_reps - actual, 0)

        if result.completed:
            status, variance = _rpe_comparison(result, prescription)
            if status is None:
                rpe_unavailable += 1
            else:
                comparable += 1
                adherent += int(status == "adherent")
                above += int(status == "above")
                below += int(status == "below")
                if variance is not None:
                    variances.append(variance)

            if prescription is None:
                top_unavailable += 1
            elif prescription.slot_role == "top_set":
                top_sets.append(TopSetPerformance(
                    result_id=result.id,
                    performed_on=started_at.date(),
                    exercise_name=result.exercise_name,
                    actual_load_kg=result.actual_load_kg,
                    actual_reps=result.actual_reps,
                    actual_rpe=result.actual_rpe,
                    rpe_status=status,
                ))

    return TrainingPerformanceSummary(
        rpe=RPEAdherence(
            comparable_sets=comparable,
            adherent_sets=adherent,
            above_sets=above,
            below_sets=below,
            unavailable_sets=rpe_unavailable,
            adherence_rate=round(adherent / comparable, 4) if comparable else None,
            mean_variance=round(sum(variances) / len(variances), 2) if variances else None,
        ),
        reps=RepCompletion(
            decided_sets=decided,
            completed_sets=completed,
            skipped_sets=skipped,
            completion_rate=round(completed / decided, 4) if decided else None,
            prescribed_reps=prescribed_reps,
            completed_reps=completed_reps,
            missed_reps=missed_reps,
            unavailable_sets=rep_unavailable,
        ),
        top_sets=tuple(reversed(top_sets)),
        top_set_unavailable=top_unavailable,
    )


def _exact_reps(value: str | None) -> int | None:
    if value is None or not value.strip().isdigit():
        return None
    return int(value)


def _rpe_comparison(
    result: TrainingSetResult,
    prescription: ExercisePrescription | None,
) -> tuple[str | None, float | None]:
    actual = result.actual_rpe
    if actual is None:
        return None, None
    if prescription is not None and prescription.rpe_min is not None and prescription.rpe_max is not None:
        if actual < prescription.rpe_min:
            return "below", actual - prescription.rpe_min
        if actual > prescription.rpe_max:
            return "above", actual - prescription.rpe_max
        return "adherent", 0.0
    if prescription is not None and prescription.rpe_cap is not None:
        return ("above", actual - prescription.rpe_cap) if actual > prescription.rpe_cap else ("adherent", 0.0)
    target = result.prescribed_rpe
    if target is None:
        return None, None
    variance = actual - target
    if variance > RPE_TOLERANCE:
        return "above", variance
    if variance < -RPE_TOLERANCE:
        return "below", variance
    return "adherent", variance
