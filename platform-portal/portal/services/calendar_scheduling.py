"""Athlete scheduling projection built from the platform's dated concepts.

This is intentionally not a generic calendar.  It joins planned training,
competition milestones, holiday/travel constraints and weekly check-in timing
without owning or mutating any of those records.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Iterable, Mapping

from ..models.checkins import AthleteCheckinSettings
from ..models.programming import TrainingBlock, TrainingSessionLog
from .holiday_mode import (
    HolidayPeriod,
    HolidayStatus,
    SessionAction,
    SessionContext,
    SessionDecision,
    decide_session,
    overlapping_periods,
)
from .training_schedule import ScheduledSession, TrainingSchedule, project_training_schedule


class CheckinState(str, Enum):
    DISABLED = "disabled"
    UPCOMING = "upcoming"
    DUE = "due"
    OVERDUE = "overdue"
    SUBMITTED = "submitted"


@dataclass(frozen=True)
class CompetitionDate:
    """A competition milestone sourced from the existing meet-day domain."""

    competition_id: int
    name: str
    occurs_on: date
    status: str = "planned"


@dataclass(frozen=True)
class CheckinTiming:
    state: CheckinState
    due_on: date | None


@dataclass(frozen=True)
class ConstrainedSession:
    scheduled: ScheduledSession
    holiday_decision: SessionDecision | None
    competition_ids: tuple[int, ...]


@dataclass(frozen=True)
class AthleteScheduling:
    training: TrainingSchedule
    sessions: tuple[ConstrainedSession, ...]
    competitions: tuple[CompetitionDate, ...]
    next_competition: CompetitionDate | None
    checkin: CheckinTiming
    holiday_conflicts: tuple[tuple[str, str], ...]


def project_checkin_timing(
    settings: AthleteCheckinSettings | None,
    submitted_week_endings: Iterable[date],
    *,
    today: date,
) -> CheckinTiming:
    """Resolve the current weekly check-in window without database queries."""
    if settings is None or not settings.workflow_active or not settings.has_enabled_modules:
        return CheckinTiming(CheckinState.DISABLED, None)
    if isinstance(settings.checkin_day, bool) or settings.checkin_day not in range(7):
        raise ValueError("check-in day must use Monday=0 through Sunday=6")

    week_start = date.fromordinal(today.toordinal() - today.weekday())
    week_end = date.fromordinal(week_start.toordinal() + 6)
    due_on = date.fromordinal(week_start.toordinal() + settings.checkin_day)
    if any(week_start <= submitted <= week_end for submitted in submitted_week_endings):
        state = CheckinState.SUBMITTED
    elif today < due_on:
        state = CheckinState.UPCOMING
    elif today == due_on:
        state = CheckinState.DUE
    else:
        state = CheckinState.OVERDUE
    return CheckinTiming(state, due_on)


def project_athlete_scheduling(
    block: TrainingBlock | None,
    logs: Mapping[int, TrainingSessionLog],
    *,
    athlete_id: int,
    today: date,
    planned_dates: Mapping[int, date] | None = None,
    competitions: Iterable[CompetitionDate] = (),
    holiday_periods: Iterable[HolidayPeriod] = (),
    session_contexts: Mapping[int, SessionContext] | None = None,
    checkin_settings: AthleteCheckinSettings | None = None,
    submitted_week_endings: Iterable[date] = (),
) -> AthleteScheduling:
    """Compose the four scheduling concerns while preserving source truth.

    Holiday decisions are overlays.  They never move a planned date or change a
    programme/log.  Multiple holidays affecting one session are reported as a
    conflict and deliberately require coach review.
    """
    training = project_training_schedule(
        block, logs, today=today, planned_dates=planned_dates
    )
    periods = tuple(
        period
        for period in holiday_periods
        if period.athlete_id == athlete_id and period.status is not HolidayStatus.CANCELLED
    )
    conflicts = overlapping_periods(periods)
    contexts = session_contexts or {}
    ordered_competitions = tuple(
        sorted(competitions, key=lambda item: (item.occurs_on, item.competition_id))
    )
    constrained: list[ConstrainedSession] = []
    for scheduled in training.sessions:
        planned_on = scheduled.planned_on
        matches = (
            tuple(p for p in periods if planned_on and p.starts_on <= planned_on <= p.ends_on)
            if planned_on
            else ()
        )
        decision = None
        if len(matches) > 1:
            decision = SessionDecision(
                SessionAction.COACH_REVIEW,
                "overlapping holiday/travel constraints",
            )
        elif matches:
            context = contexts.get(scheduled.session.id, SessionContext(planned_on))
            if context.scheduled_on != planned_on:
                raise ValueError("session context date must match its planned date")
            decision = decide_session(matches[0], context)
        competition_ids = tuple(
            item.competition_id
            for item in ordered_competitions
            if planned_on is not None and item.occurs_on == planned_on
        )
        constrained.append(ConstrainedSession(scheduled, decision, competition_ids))

    next_competition = next(
        (
            item for item in ordered_competitions
            if item.occurs_on >= today and item.status != "complete"
        ),
        None,
    )
    return AthleteScheduling(
        training=training,
        sessions=tuple(constrained),
        competitions=ordered_competitions,
        next_competition=next_competition,
        checkin=project_checkin_timing(
            checkin_settings, submitted_week_endings, today=today
        ),
        holiday_conflicts=conflicts,
    )
