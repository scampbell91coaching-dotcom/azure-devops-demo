"""Deterministic, read-only SBD performance analytics.

The service deliberately derives metrics from completed training logs and the
existing lift-slot taxonomy.  It does not guess a lift family from exercise
names, so older or deleted prescriptions are reported as incomplete data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from ..models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)

_LIFTS = ("squat", "bench", "deadlift")
_KG = Decimal("0.01")


@dataclass(frozen=True)
class PerformanceFilter:
    block_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True)
class E1RMPoint:
    performed_on: date
    lift_family: str
    e1rm_kg: Decimal
    load_kg: Decimal
    reps: int
    actual_rpe: Decimal | None
    session_log_id: int
    set_result_id: int
    is_top_set: bool
    formula: str = "Epley: load × (1 + reps / 30)"


@dataclass(frozen=True)
class VolumePoint:
    performed_on: date
    lift_family: str
    volume_kg: Decimal
    completed_sets: int


@dataclass(frozen=True)
class PerformanceDataQuality:
    completed_sets_seen: int
    sets_missing_lift_family: int
    sets_missing_load_or_reps: int
    top_sets_outside_e1rm_rep_range: int
    notes: tuple[str, ...]


@dataclass(frozen=True)
class SBDPerformanceAnalytics:
    athlete_id: int
    filters: PerformanceFilter
    e1rm_trend: tuple[E1RMPoint, ...]
    training_volume: tuple[VolumePoint, ...]
    data_quality: PerformanceDataQuality


def build_sbd_performance_analytics(
    athlete_id: int,
    *,
    block_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> SBDPerformanceAnalytics:
    """Return e1RM and volume for one athlete from completed session logs.

    Volume is actual load times actual reps for every completed, classified SBD
    set.  e1RM uses the best eligible top set per lift and completed session;
    Epley is limited to 1–12 reps because higher-rep estimates are not presented
    as decision-grade strength data.  Extra sets attached to a top-set
    prescription remain top sets, matching the persisted domain relationship.
    """
    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError("date_from cannot be after date_to")
    if block_id is not None and not TrainingBlock.query.filter_by(
        id=block_id, athlete_id=athlete_id
    ).first():
        raise ValueError("block_id does not belong to athlete")

    query = (
        TrainingSetResult.query.with_entities(
            TrainingSetResult.id,
            TrainingSessionLog.id,
            TrainingSessionLog.completed_at,
            TrainingSetResult.actual_load_kg,
            TrainingSetResult.actual_reps,
            TrainingSetResult.actual_rpe,
            ExercisePrescription.slot_role,
            ProgrammingLiftSlot.lift_family,
        )
        .join(TrainingSessionLog, TrainingSetResult.session_log_id == TrainingSessionLog.id)
        .outerjoin(
            ExercisePrescription,
            TrainingSetResult.prescription_id == ExercisePrescription.id,
        )
        .outerjoin(
            ProgrammingLiftSlot,
            ExercisePrescription.lift_slot_id == ProgrammingLiftSlot.id,
        )
        .filter(
            TrainingSessionLog.athlete_id == athlete_id,
            TrainingSessionLog.status == "completed",
            TrainingSessionLog.completed_at.isnot(None),
            TrainingSetResult.completed.is_(True),
        )
    )
    if block_id is not None:
        query = query.join(
            TrainingSession, TrainingSessionLog.session_id == TrainingSession.id
        ).join(TrainingWeek, TrainingSession.week_id == TrainingWeek.id).filter(
            TrainingWeek.block_id == block_id
        )
    if date_from is not None:
        query = query.filter(
            TrainingSessionLog.completed_at >= datetime.combine(date_from, time.min)
        )
    if date_to is not None:
        query = query.filter(
            TrainingSessionLog.completed_at
            < datetime.combine(date_to + timedelta(days=1), time.min)
        )

    rows = query.order_by(
        TrainingSessionLog.completed_at,
        TrainingSessionLog.id,
        TrainingSetResult.id,
    ).all()
    volume: dict[tuple[date, str], tuple[Decimal, int]] = {}
    best: dict[tuple[int, str], E1RMPoint] = {}
    missing_family = missing_inputs = high_rep = 0

    for row in rows:
        result_id, log_id, completed_at, load, reps, rpe, role, family = row
        if family not in _LIFTS:
            missing_family += 1
            continue
        if load is None or reps is None or load <= 0 or reps <= 0:
            missing_inputs += 1
            continue
        performed_on = completed_at.date()
        load_decimal = Decimal(str(load))
        volume_key = (performed_on, family)
        current_volume, current_sets = volume.get(volume_key, (Decimal("0"), 0))
        volume[volume_key] = (current_volume + load_decimal * reps, current_sets + 1)

        if role != "top_set":
            continue
        if reps > 12:
            high_rep += 1
            continue
        estimate = (load_decimal * (Decimal("1") + Decimal(reps) / Decimal("30"))).quantize(
            _KG, rounding=ROUND_HALF_UP
        )
        point = E1RMPoint(
            performed_on=performed_on,
            lift_family=family,
            e1rm_kg=estimate,
            load_kg=load_decimal.quantize(_KG, rounding=ROUND_HALF_UP),
            reps=reps,
            actual_rpe=(
                Decimal(str(rpe)).quantize(_KG, rounding=ROUND_HALF_UP)
                if rpe is not None
                else None
            ),
            session_log_id=log_id,
            set_result_id=result_id,
            is_top_set=True,
        )
        key = (log_id, family)
        incumbent = best.get(key)
        if incumbent is None or (point.e1rm_kg, -point.set_result_id) > (
            incumbent.e1rm_kg,
            -incumbent.set_result_id,
        ):
            best[key] = point

    volume_points = tuple(
        VolumePoint(day, family, total.quantize(_KG, rounding=ROUND_HALF_UP), sets)
        for (day, family), (total, sets) in sorted(
            volume.items(), key=lambda item: (item[0][0], _LIFTS.index(item[0][1]))
        )
    )
    e1rm_points = tuple(
        sorted(
            best.values(),
            key=lambda item: (
                item.performed_on,
                _LIFTS.index(item.lift_family),
                item.session_log_id,
            ),
        )
    )
    notes: list[str] = []
    if not rows:
        notes.append("No completed training sets exist in the selected window.")
    if missing_family:
        notes.append(
            f"{missing_family} completed set(s) were excluded because no persisted SBD lift family was available."
        )
    if missing_inputs:
        notes.append(
            f"{missing_inputs} classified SBD set(s) were excluded because actual load or reps were missing or zero."
        )
    if high_rep:
        notes.append(
            f"{high_rep} top set(s) contributed to volume but not e1RM because they exceeded 12 reps."
        )
    return SBDPerformanceAnalytics(
        athlete_id=athlete_id,
        filters=PerformanceFilter(block_id, date_from, date_to),
        e1rm_trend=e1rm_points,
        training_volume=volume_points,
        data_quality=PerformanceDataQuality(
            len(rows), missing_family, missing_inputs, high_rep, tuple(notes)
        ),
    )
