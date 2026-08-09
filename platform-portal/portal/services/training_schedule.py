"""Read-only calendar projection for ordered training programming."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
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
        return TrainingSchedule((), None, None, None, False)
    dates = planned_dates or {}
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
    )
