"""Chart-ready, athlete-scoped coaching performance aggregates.

The service deliberately reports gaps in historical data instead of inferring lift
families, rep targets, or programme membership from exercise names.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from ..extensions import db
from ..models.athlete import Athlete
from ..models.checkins import WeeklyCheckin
from ..models.meet_day import Meet, MeetEntry
from ..models.nutrition_checkin import NutritionCheckIn
from ..models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)

LIFTS = ("squat", "bench", "deadlift")
RPE_TOLERANCE = 0.5
Availability = Literal["available", "partial", "unavailable"]


@dataclass(frozen=True)
class MetricAvailability:
    status: Availability
    explanation: str
    included: int = 0
    excluded: int = 0


@dataclass(frozen=True)
class BlockOption:
    id: int
    name: str
    status: str


@dataclass(frozen=True)
class LiftPoint:
    recorded_on: date
    lift: str
    value: float
    session_log_id: int


@dataclass(frozen=True)
class RpePoint:
    recorded_on: date
    lift: str
    prescribed: float
    actual: float
    delta: float
    adherent: bool


@dataclass(frozen=True)
class RepSummary:
    completed: int
    missed: int
    unmeasurable_sets: int


@dataclass(frozen=True)
class AdherenceSummary:
    adherent: int
    measured: int
    rate: float | None
    tolerance: float


@dataclass(frozen=True)
class BodyweightPoint:
    recorded_on: date
    value_kg: float
    source: str


@dataclass(frozen=True)
class MeetContext:
    meet_id: int
    name: str
    meet_date: date
    days_remaining: int
    weight_class: str | None
    latest_bodyweight_kg: float | None
    distance_to_class_kg: float | None


@dataclass(frozen=True)
class CoachDecision:
    level: Literal["attention", "watch", "positive", "insufficient_data"]
    action: str
    rationale: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class PerformanceAvailability:
    e1rm: MetricAvailability
    volume: MetricAvailability
    rpe: MetricAvailability
    reps: MetricAvailability
    top_sets: MetricAvailability
    bodyweight: MetricAvailability


@dataclass(frozen=True)
class AthletePerformance:
    athlete_id: int
    generated_on: date
    selected_block_id: int | None
    blocks: tuple[BlockOption, ...]
    e1rm_trend: tuple[LiftPoint, ...]
    volume_trend: tuple[LiftPoint, ...]
    rpe_trend: tuple[RpePoint, ...]
    rpe_adherence: AdherenceSummary
    reps: RepSummary
    top_set_performance: tuple[LiftPoint, ...]
    bodyweight_trend: tuple[BodyweightPoint, ...]
    meet: MeetContext | None
    decisions: tuple[CoachDecision, ...]
    availability: PerformanceAvailability


@dataclass(frozen=True)
class _SetRow:
    log_id: int
    recorded_on: date
    lift: str | None
    slot_role: str | None
    is_extra: bool
    completed: bool
    skipped: bool
    prescribed_reps: str | None
    load: float | None
    reps: int | None
    prescribed_rpe: float | None
    actual_rpe: float | None


def get_athlete_performance(
    athlete_id: int, *, today: date | None = None, block_id: int | None = None
) -> AthletePerformance | None:
    """Build one athlete's performance contract; every query is athlete scoped."""
    today = today or datetime.now(UTC).date()
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        return None

    blocks = tuple(
        BlockOption(item.id, item.name, item.status)
        for item in TrainingBlock.query.filter_by(athlete_id=athlete_id)
        .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
        .all()
    )
    if block_id is not None and block_id not in {item.id for item in blocks}:
        raise ValueError("The selected training block does not belong to this athlete.")

    rows = _training_rows(athlete_id, block_id)
    bodyweight = _bodyweight_points(athlete_id)
    meet = _meet_context(athlete_id, today, bodyweight, athlete)

    attributed = [row for row in rows if row.lift in LIFTS]
    unattributed = len(rows) - len(attributed)
    completed = [row for row in attributed if row.completed]
    loadable = [row for row in completed if row.load is not None and row.reps is not None]

    e1rm = tuple(
        LiftPoint(row.recorded_on, row.lift, round(row.load * (1 + row.reps / 30), 1), row.log_id)
        for row in loadable
        if row.load > 0 and row.reps > 0 and row.reps <= 12
    )
    volume = _daily_lift_points(loadable, lambda row: row.load * row.reps)
    rpe_rows = [
        row for row in completed
        if row.prescribed_rpe is not None and row.actual_rpe is not None
    ]
    rpe = tuple(
        RpePoint(
            row.recorded_on, row.lift, row.prescribed_rpe, row.actual_rpe,
            round(row.actual_rpe - row.prescribed_rpe, 2),
            abs(row.actual_rpe - row.prescribed_rpe) <= RPE_TOLERANCE,
        )
        for row in rpe_rows
    )
    adherent = sum(point.adherent for point in rpe)
    adherence = AdherenceSummary(
        adherent=adherent,
        measured=len(rpe),
        rate=round(adherent / len(rpe), 3) if rpe else None,
        tolerance=RPE_TOLERANCE,
    )
    reps, unmeasurable = _rep_summary(attributed)
    top_sets = tuple(
        LiftPoint(row.recorded_on, row.lift, round(row.load * (1 + row.reps / 30), 1), row.log_id)
        for row in loadable
        if row.slot_role == "top_set" and row.load > 0 and row.reps > 0 and row.reps <= 12
    )

    availability = PerformanceAvailability(
        e1rm=_availability(len(e1rm), len(completed) - len(e1rm) + unattributed, "completed sets need a canonical lift, load, and 1-12 reps"),
        volume=_availability(len(loadable), len(completed) - len(loadable) + unattributed, "completed sets need a canonical lift, load, and reps"),
        rpe=_availability(len(rpe), len(completed) - len(rpe) + unattributed, "completed sets need both prescribed and actual RPE"),
        reps=_availability(len(attributed) - unmeasurable, unmeasurable + unattributed, "missed reps require an exact snapshotted rep target"),
        top_sets=_availability(len(top_sets), len(completed) - len(top_sets) + unattributed, "top sets require V7 lift-slot metadata, load, and 1-12 reps"),
        bodyweight=_availability(len(bodyweight), 0, "bodyweight requires a recorded weekly or nutrition check-in"),
    )
    decisions = _decisions(adherence, reps, rpe, e1rm, meet, availability)
    return AthletePerformance(
        athlete_id=athlete_id,
        generated_on=today,
        selected_block_id=block_id,
        blocks=blocks,
        e1rm_trend=e1rm,
        volume_trend=volume,
        rpe_trend=rpe,
        rpe_adherence=adherence,
        reps=reps,
        top_set_performance=top_sets,
        bodyweight_trend=bodyweight,
        meet=meet,
        decisions=decisions,
        availability=availability,
    )


def _training_rows(athlete_id: int, block_id: int | None) -> list[_SetRow]:
    query = (
        db.session.query(
            TrainingSessionLog.id,
            TrainingSessionLog.completed_at,
            TrainingSetResult.completed,
            TrainingSetResult.skipped,
            TrainingSetResult.is_extra,
            TrainingSetResult.prescribed_reps,
            TrainingSetResult.actual_load_kg,
            TrainingSetResult.actual_reps,
            TrainingSetResult.prescribed_rpe,
            TrainingSetResult.actual_rpe,
            ProgrammingLiftSlot.lift_family,
            ExercisePrescription.slot_role,
        )
        .join(TrainingSetResult, TrainingSetResult.session_log_id == TrainingSessionLog.id)
        .outerjoin(ExercisePrescription, ExercisePrescription.id == TrainingSetResult.prescription_id)
        .outerjoin(ProgrammingLiftSlot, ProgrammingLiftSlot.id == ExercisePrescription.lift_slot_id)
        .filter(
            TrainingSessionLog.athlete_id == athlete_id,
            TrainingSessionLog.status == "completed",
            TrainingSessionLog.completed_at.is_not(None),
        )
    )
    if block_id is not None:
        query = (
            query.join(TrainingSession, TrainingSession.id == TrainingSessionLog.session_id)
            .join(TrainingWeek, TrainingWeek.id == TrainingSession.week_id)
            .filter(TrainingWeek.block_id == block_id)
        )
    raw = query.order_by(TrainingSessionLog.completed_at, TrainingSetResult.id).all()
    return [
        _SetRow(
            item[0], item[1].date(), item[10], item[11], bool(item[4]),
            bool(item[2]), bool(item[3]), item[5], item[6], item[7], item[8], item[9],
        )
        for item in raw
    ]


def _daily_lift_points(rows: list[_SetRow], value) -> tuple[LiftPoint, ...]:
    totals: dict[tuple[date, str, int], float] = {}
    for row in rows:
        key = (row.recorded_on, row.lift, row.log_id)
        totals[key] = totals.get(key, 0.0) + value(row)
    return tuple(LiftPoint(day, lift, round(total, 1), log_id) for (day, lift, log_id), total in totals.items())


def _exact_reps(value: str | None) -> int | None:
    if value is None:
        return None
    stripped = value.strip()
    return int(stripped) if stripped.isdigit() else None


def _rep_summary(rows: list[_SetRow]) -> tuple[RepSummary, int]:
    completed = missed = unmeasurable = 0
    for row in rows:
        target = _exact_reps(row.prescribed_reps)
        if row.completed and row.reps is not None:
            completed += row.reps
            if row.is_extra:
                continue
            if target is not None:
                missed += max(0, target - row.reps)
            else:
                unmeasurable += 1
        elif row.skipped:
            if row.is_extra:
                continue
            if target is not None:
                missed += target
            else:
                unmeasurable += 1
        else:
            unmeasurable += 1
    return RepSummary(completed, missed, unmeasurable), unmeasurable


def _bodyweight_points(athlete_id: int) -> tuple[BodyweightPoint, ...]:
    weekly = WeeklyCheckin.query.filter(
        WeeklyCheckin.athlete_id == athlete_id,
        WeeklyCheckin.average_bodyweight_kg.is_not(None),
    ).all()
    nutrition = NutritionCheckIn.query.filter(
        NutritionCheckIn.athlete_id == athlete_id,
        NutritionCheckIn.bodyweight_kg.is_not(None),
    ).all()
    points = [BodyweightPoint(item.week_ending, float(item.average_bodyweight_kg), "weekly_checkin") for item in weekly]
    points.extend(BodyweightPoint(item.checkin_date, float(item.bodyweight_kg), "nutrition_checkin") for item in nutrition)
    return tuple(sorted(points, key=lambda point: (point.recorded_on, point.source)))


def _meet_context(athlete_id: int, today: date, bodyweight: tuple[BodyweightPoint, ...], athlete: Athlete) -> MeetContext | None:
    item = (
        db.session.query(MeetEntry, Meet)
        .join(Meet, Meet.id == MeetEntry.meet_id)
        .filter(MeetEntry.athlete_id == athlete_id, Meet.status.in_(("planned", "active")), Meet.meet_date >= today)
        .order_by(Meet.meet_date, Meet.id)
        .first()
    )
    if item is None:
        return None
    entry, meet = item
    latest = bodyweight[-1].value_kg if bodyweight else athlete.bodyweight_kg
    class_limit = _weight_class_limit(meet.weight_class or athlete.weight_class)
    return MeetContext(
        meet_id=meet.id, name=meet.name, meet_date=meet.meet_date,
        days_remaining=(meet.meet_date - today).days,
        weight_class=meet.weight_class or athlete.weight_class,
        latest_bodyweight_kg=latest,
        distance_to_class_kg=round(latest - class_limit, 2) if latest is not None and class_limit is not None else None,
    )


def _weight_class_limit(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = value.casefold().replace("kg", "").strip()
    if cleaned.endswith("+"):
        return None
    try:
        result = float(cleaned)
    except ValueError:
        return None
    return result if result > 0 else None


def _availability(included: int, excluded: int, requirement: str) -> MetricAvailability:
    if included == 0:
        return MetricAvailability("unavailable", f"No usable data; {requirement}.", included, excluded)
    if excluded:
        return MetricAvailability("partial", f"Some history excluded because {requirement}.", included, excluded)
    return MetricAvailability("available", "All relevant persisted records were usable.", included, 0)


def _decisions(adherence, reps, rpe, e1rm, meet, availability) -> tuple[CoachDecision, ...]:
    decisions: list[CoachDecision] = []
    if reps.missed > 0:
        decisions.append(CoachDecision("attention", "Review load or rep prescription before the next exposure.", "The athlete missed prescribed reps.", (f"{reps.missed} missed reps",)))
    if adherence.measured >= 3 and adherence.rate < 0.7:
        average_delta = round(sum(point.delta for point in rpe) / len(rpe), 2)
        decisions.append(CoachDecision("watch", "Review RPE calibration and recent loading.", "RPE adherence is below 70% across at least three measured sets.", (f"{adherence.adherent}/{adherence.measured} within ±{adherence.tolerance:g}", f"mean delta {average_delta:+g}")))
    if meet and meet.days_remaining <= 28 and meet.distance_to_class_kg is not None and meet.distance_to_class_kg > 0:
        decisions.append(CoachDecision("attention", "Confirm the meet weight-making plan.", "Bodyweight is above the recorded class limit inside four weeks.", (f"{meet.days_remaining} days to meet", f"{meet.distance_to_class_kg:g} kg above class")))
    if not decisions and len(e1rm) >= 3 and adherence.measured >= 3 and adherence.rate >= 0.7:
        decisions.append(CoachDecision("positive", "Continue the current progression and monitor the next top set.", "Recent performance has enough reliable loading and RPE evidence with acceptable adherence.", (f"{len(e1rm)} e1RM observations", f"{adherence.rate:.0%} RPE adherence")))
    if not decisions:
        unavailable = sum(getattr(availability, name).status == "unavailable" for name in ("e1rm", "rpe", "reps"))
        decisions.append(CoachDecision("insufficient_data", "Collect complete load, reps, and RPE on upcoming SBD sets.", "There is not enough reliable evidence for a progression or regression decision.", (f"{unavailable}/3 core decision inputs unavailable",)))
    return tuple(decisions)
