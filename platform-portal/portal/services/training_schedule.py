"""Read-only calendar projection for ordered training programming."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Mapping

from ..models.programming import TrainingBlock, TrainingSession, TrainingSessionLog, TrainingWeek


@dataclass(frozen=True)
class ScheduledSession:
    session: TrainingSession
    planned_on: date | None
    completed: bool

    def timing_label(self, today: date) -> str:
        if self.planned_on is None:
            return "Date not set · programme order"
        if self.planned_on == today:
            return f"Today · {self.planned_on.strftime('%d %b %Y')}"
        if self.planned_on < today:
            return f"Overdue · {self.planned_on.strftime('%d %b %Y')}"
        return self.planned_on.strftime("%A · %d %b %Y")


@dataclass(frozen=True)
class TrainingSchedule:
    sessions: tuple[ScheduledSession, ...]
    current_week: TrainingWeek | None
    today_session: ScheduledSession | None
    next_session: ScheduledSession | None
    has_planned_dates: bool
    programme_start: date | None
    programme_end: date | None
    timezone: str


def local_today(timezone_name: str, *, now=None) -> date:
    """Return today in the programme's explicit IANA timezone."""
    from datetime import UTC, datetime
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Unknown programme timezone.") from error
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return instant.astimezone(zone).date()


def programme_dates(block: TrainingBlock) -> dict[int, date]:
    """Project ordered sessions into their week window from one domain anchor."""
    if block.start_date is None:
        return {}
    return {
        session.id: block.start_date + timedelta(weeks=week.position - 1, days=session.position - 1)
        for week in block.weeks for session in week.sessions
    }


def project_training_schedule(
    block: TrainingBlock | None,
    logs: Mapping[int, TrainingSessionLog],
    *,
    today: date,
    planned_dates: Mapping[int, date] | None = None,
) -> TrainingSchedule:
    """Project schedule state without mutating published programming.

    A later Holiday/Travel Mode can provide adjusted ``planned_dates`` here;
    the persisted session order and prescriptions remain untouched.
    """
    if block is None:
        return TrainingSchedule((), None, None, None, False, None, None, "UTC")
    dates = planned_dates if planned_dates is not None else programme_dates(block)
    ordered = tuple(
        ScheduledSession(
            session,
            dates.get(session.id),
            bool(logs.get(session.id) and logs[session.id].status == "completed"),
        )
        for week in block.weeks
        for session in week.sessions
    )
    incomplete = [item for item in ordered if not item.completed]
    dated = [item for item in incomplete if item.planned_on is not None]
    next_item = (
        min(dated, key=lambda item: (item.planned_on, item.session.week.position, item.session.position))
        if dated else (incomplete[0] if incomplete else None)
    )
    return TrainingSchedule(
        ordered,
        next_item.session.week if next_item else None,
        next((item for item in dated if item.planned_on == today), None),
        next_item,
        bool(dated),
        block.start_date,
        block.end_date,
        block.timezone or "UTC",
    )
