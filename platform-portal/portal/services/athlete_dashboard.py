from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import joinedload, selectinload

from ..extensions import db
from ..models.athlete import Athlete
from ..models.checkins import AthleteCheckinSettings, WeeklyCheckin
from ..models.nutrition_checkin import NutritionCheckIn
from ..models.programming import (
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingWeek,
)


@dataclass(frozen=True)
class CoachResponse:
    body: str
    responded_at: datetime


@dataclass(frozen=True)
class TrendPoint:
    recorded_on: date
    value: float


@dataclass(frozen=True)
class AthleteDashboard:
    athlete: Athlete
    current_block: TrainingBlock | None
    current_week: TrainingWeek | None
    next_session: TrainingSession | None
    latest_checkin: WeeklyCheckin | None
    recent_checkins: tuple[WeeklyCheckin, ...]
    next_checkin_date: date | None
    latest_nutrition: NutritionCheckIn | None
    latest_bodyweight_kg: float | None
    bodyweight_trend: tuple[TrendPoint, ...]
    performance_trend: tuple[TrendPoint, ...]
    nutrition_history: tuple[NutritionCheckIn, ...]
    latest_coach_response: CoachResponse | None


def get_athlete_dashboard(athlete_id: int, *, today: date) -> AthleteDashboard | None:
    """Return dashboard data scoped to exactly one authenticated athlete."""
    athlete = db.session.get(Athlete, athlete_id)
    if athlete is None:
        return None

    current_block = (
        TrainingBlock.query.options(
            selectinload(TrainingBlock.weeks).selectinload(TrainingWeek.sessions)
        )
        .filter(
            TrainingBlock.athlete_id == athlete_id,
            TrainingBlock.status == "active",
        )
        .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
        .first()
    )
    next_session = _next_session(current_block, athlete_id)
    current_week = next_session.week if next_session is not None else None

    recent_checkins = tuple(
        WeeklyCheckin.query.filter_by(athlete_id=athlete_id)
        .order_by(WeeklyCheckin.submitted_at.desc(), WeeklyCheckin.id.desc())
        .limit(4)
        .all()
    )
    latest_checkin = recent_checkins[0] if recent_checkins else None
    settings = AthleteCheckinSettings.query.filter_by(athlete_id=athlete_id).first()
    next_checkin_date = _next_checkin_date(settings, latest_checkin, today)

    latest_nutrition = (
        NutritionCheckIn.query.options(joinedload(NutritionCheckIn.athlete))
        .filter_by(athlete_id=athlete_id)
        .order_by(NutritionCheckIn.submitted_at.desc(), NutritionCheckIn.id.desc())
        .first()
    )
    bodyweight_trend = _bodyweight_trend(athlete_id)

    return AthleteDashboard(
        athlete=athlete,
        current_block=current_block,
        current_week=current_week,
        next_session=next_session,
        latest_checkin=latest_checkin,
        recent_checkins=recent_checkins,
        next_checkin_date=next_checkin_date,
        latest_nutrition=latest_nutrition,
        latest_bodyweight_kg=(
            bodyweight_trend[-1].value if bodyweight_trend else athlete.bodyweight_kg
        ),
        bodyweight_trend=bodyweight_trend,
        performance_trend=_performance_trend(athlete_id),
        nutrition_history=_nutrition_history(athlete_id),
        latest_coach_response=_latest_coach_response(athlete_id),
    )


def _nutrition_history(athlete_id: int) -> tuple[NutritionCheckIn, ...]:
    items = (
        NutritionCheckIn.query.filter_by(athlete_id=athlete_id)
        .order_by(NutritionCheckIn.checkin_date.desc(), NutritionCheckIn.id.desc())
        .limit(12)
        .all()
    )
    for index, item in enumerate(items):
        older = items[index + 1] if index + 1 < len(items) else None
        item.weekly_bodyweight_change_kg = (
            round(item.bodyweight_kg - older.bodyweight_kg, 2)
            if older is not None
            and item.bodyweight_kg is not None
            and older.bodyweight_kg is not None
            else None
        )
    return tuple(items)


def _bodyweight_trend(athlete_id: int) -> tuple[TrendPoint, ...]:
    weekly = (
        WeeklyCheckin.query.filter(
            WeeklyCheckin.athlete_id == athlete_id,
            WeeklyCheckin.average_bodyweight_kg.isnot(None),
        )
        .order_by(WeeklyCheckin.submitted_at.desc(), WeeklyCheckin.id.desc())
        .limit(6)
        .all()
    )
    nutrition = (
        NutritionCheckIn.query.filter(
            NutritionCheckIn.athlete_id == athlete_id,
            NutritionCheckIn.bodyweight_kg.isnot(None),
        )
        .order_by(NutritionCheckIn.submitted_at.desc(), NutritionCheckIn.id.desc())
        .limit(6)
        .all()
    )
    points = [
        TrendPoint(item.week_ending, item.average_bodyweight_kg) for item in weekly
    ] + [TrendPoint(item.submitted_at.date(), item.bodyweight_kg) for item in nutrition]
    return tuple(sorted(points, key=lambda point: point.recorded_on)[-6:])


def _performance_trend(athlete_id: int) -> tuple[TrendPoint, ...]:
    items = (
        NutritionCheckIn.query.filter_by(athlete_id=athlete_id)
        .order_by(NutritionCheckIn.submitted_at.desc(), NutritionCheckIn.id.desc())
        .limit(6)
        .all()
    )
    return tuple(
        reversed(
            [
                TrendPoint(item.submitted_at.date(), item.training_performance)
                for item in items
            ]
        )
    )


def _next_session(
    block: TrainingBlock | None, athlete_id: int
) -> TrainingSession | None:
    if block is None:
        return None
    completed_ids = {
        session_id
        for (session_id,) in db.session.query(TrainingSessionLog.session_id)
        .filter_by(athlete_id=athlete_id, status="completed")
        .filter(TrainingSessionLog.session_id.is_not(None))
        .all()
    }
    return next(
        (
            session
            for week in block.weeks
            for session in week.sessions
            if session.id not in completed_ids
        ),
        None,
    )


def _next_checkin_date(
    settings: AthleteCheckinSettings | None,
    latest: WeeklyCheckin | None,
    today: date,
) -> date | None:
    if (
        settings is None
        or not settings.workflow_active
        or not settings.has_enabled_modules
    ):
        return None

    days_ahead = (settings.checkin_day - today.weekday()) % 7
    candidate = today + timedelta(days=days_ahead)
    if latest is not None:
        candidate_week_start = candidate - timedelta(days=candidate.weekday())
        latest_week_start = latest.week_ending - timedelta(
            days=latest.week_ending.weekday()
        )
        if latest_week_start >= candidate_week_start:
            candidate += timedelta(days=7)
    return candidate


def _latest_coach_response(
    athlete_id: int,
) -> CoachResponse | None:
    weekly = (
        WeeklyCheckin.query.filter(
            WeeklyCheckin.athlete_id == athlete_id,
            WeeklyCheckin.coach_notes.isnot(None),
            WeeklyCheckin.coach_notes != "",
        )
        .order_by(
            WeeklyCheckin.coach_reviewed_at.desc(),
            WeeklyCheckin.submitted_at.desc(),
            WeeklyCheckin.id.desc(),
        )
        .first()
    )
    responses: list[CoachResponse] = []
    if weekly is not None:
        responses.append(
            CoachResponse(
                body=weekly.coach_notes,
                responded_at=weekly.coach_reviewed_at or weekly.submitted_at,
            )
        )
    nutrition = (
        NutritionCheckIn.query.filter(
            NutritionCheckIn.athlete_id == athlete_id,
            NutritionCheckIn.coach_response.isnot(None),
            NutritionCheckIn.coach_response != "",
        )
        .order_by(
            NutritionCheckIn.submitted_at.desc(),
            NutritionCheckIn.id.desc(),
        )
        .first()
    )
    if nutrition is not None:
        responses.append(
            CoachResponse(
                body=nutrition.coach_response,
                responded_at=nutrition.submitted_at,
            )
        )
    return max(responses, key=lambda response: response.responded_at, default=None)
