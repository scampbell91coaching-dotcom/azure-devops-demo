"""Schema-independent holiday/travel scheduling policy.

The objects here are deliberately detached from Flask and SQLAlchemy.  They form
the contract for a future persistence adapter and return presentation/generation
instructions; they never edit a published programme.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from enum import Enum
from typing import Iterable


class TrainingAvailability(str, Enum):
    NORMAL = "normal"
    REDUCED = "reduced"
    NONE = "none"


class ProgrammingIntent(str, Enum):
    PRESERVE = "preserve"
    REDUCE = "reduce"
    SUBSTITUTE = "substitute"
    PAUSE = "pause"


class HolidayStatus(str, Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Provenance(str, Enum):
    ATHLETE_SUBMITTED = "athlete_submitted"
    COACH_ENTERED = "coach_entered"


class TemporalState(str, Enum):
    UPCOMING = "upcoming"
    ACTIVE = "active"
    PAST = "past"
    CANCELLED = "cancelled"


class SessionAction(str, Enum):
    PRESENT_ORIGINAL = "present_original"
    PRESENT_ORIGINAL_AWAY = "present_original_away"
    OMIT_FROM_HOLIDAY_VIEW = "omit_from_holiday_view"
    PROPOSE_REDUCED = "propose_reduced"
    PROPOSE_SUBSTITUTE = "propose_substitute"
    COACH_REVIEW = "coach_review"


@dataclass(frozen=True)
class CoachOverride:
    actor: str
    reason: str
    availability: TrainingAvailability | None = None
    available_training_days: frozenset[int] | None = None
    equipment: frozenset[str] | None = None
    programming_intent: ProgrammingIntent | None = None

    def __post_init__(self) -> None:
        if not self.actor.strip() or not self.reason.strip():
            raise ValueError("coach override requires actor and reason")
        _validate_days(self.available_training_days)


@dataclass(frozen=True)
class HolidayPeriod:
    holiday_id: str
    athlete_id: int
    starts_on: date
    ends_on: date
    availability: TrainingAvailability
    programming_intent: ProgrammingIntent
    provenance: Provenance
    status: HolidayStatus = HolidayStatus.PLANNED
    available_training_days: frozenset[int] = field(default_factory=frozenset)
    equipment: frozenset[str] = field(default_factory=frozenset)
    location: str | None = None
    time_zone: str | None = None
    bodyweight_intent: str | None = None
    nutrition_intent: str | None = None
    notes: str | None = None
    return_to_training_on: date | None = None
    coach_override: CoachOverride | None = None

    def __post_init__(self) -> None:
        if not self.holiday_id.strip() or self.athlete_id < 1:
            raise ValueError("holiday id and positive athlete id are required")
        if self.ends_on < self.starts_on:
            raise ValueError("holiday end cannot precede its start")
        if self.return_to_training_on and self.return_to_training_on <= self.ends_on:
            raise ValueError("return-to-training date must be after the holiday")
        _validate_days(self.available_training_days)
        if self.availability is TrainingAvailability.NONE and self.available_training_days:
            raise ValueError("no-training holidays cannot have available training days")
        if self.availability is TrainingAvailability.NONE and self.programming_intent is not ProgrammingIntent.PAUSE:
            raise ValueError("no-training holidays require pause intent")

    @property
    def effective_return_date(self) -> date:
        return self.return_to_training_on or self.ends_on + timedelta(days=1)

    def effective(self) -> HolidayPeriod:
        override = self.coach_override
        if override is None:
            return self
        return replace(
            self,
            availability=override.availability or self.availability,
            available_training_days=(override.available_training_days
                                     if override.available_training_days is not None
                                     else self.available_training_days),
            equipment=override.equipment if override.equipment is not None else self.equipment,
            programming_intent=override.programming_intent or self.programming_intent,
            coach_override=None,
        )

    def temporal_state(self, as_of: date) -> TemporalState:
        if self.status is HolidayStatus.CANCELLED:
            return TemporalState.CANCELLED
        if as_of < self.starts_on:
            return TemporalState.UPCOMING
        if as_of <= self.ends_on and self.status is not HolidayStatus.COMPLETED:
            return TemporalState.ACTIVE
        return TemporalState.PAST


@dataclass(frozen=True)
class SessionContext:
    scheduled_on: date
    required_equipment: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SessionDecision:
    action: SessionAction
    reason: str
    preserve_original: bool = True


def overlapping_periods(periods: Iterable[HolidayPeriod]) -> tuple[tuple[str, str], ...]:
    """Return deterministic inclusive-date conflicts for the same athlete."""
    active = sorted(
        (p for p in periods if p.status is not HolidayStatus.CANCELLED),
        key=lambda p: (p.athlete_id, p.starts_on, p.ends_on, p.holiday_id),
    )
    conflicts: list[tuple[str, str]] = []
    for index, left in enumerate(active):
        for right in active[index + 1:]:
            if right.athlete_id != left.athlete_id:
                continue
            if right.starts_on > left.ends_on:
                break
            conflicts.append((left.holiday_id, right.holiday_id))
    return tuple(conflicts)


def decide_session(period: HolidayPeriod, session: SessionContext) -> SessionDecision:
    """Produce a non-mutating instruction for Block Factory/presentation."""
    event = period.effective()
    if not event.starts_on <= session.scheduled_on <= event.ends_on:
        return SessionDecision(SessionAction.PRESENT_ORIGINAL, "outside holiday dates")
    if event.availability is TrainingAvailability.NONE:
        return SessionDecision(SessionAction.OMIT_FROM_HOLIDAY_VIEW, "training unavailable; programme retained")
    if event.available_training_days and session.scheduled_on.weekday() not in event.available_training_days:
        return SessionDecision(SessionAction.OMIT_FROM_HOLIDAY_VIEW, "day is unavailable; programme retained")

    missing = session.required_equipment - event.equipment
    if missing:
        if event.programming_intent is ProgrammingIntent.SUBSTITUTE:
            return SessionDecision(SessionAction.PROPOSE_SUBSTITUTE, f"missing equipment: {', '.join(sorted(missing))}")
        return SessionDecision(SessionAction.COACH_REVIEW, f"missing equipment: {', '.join(sorted(missing))}")
    if event.availability is TrainingAvailability.REDUCED or event.programming_intent is ProgrammingIntent.REDUCE:
        return SessionDecision(SessionAction.PROPOSE_REDUCED, "reduced training availability")
    if event.programming_intent is ProgrammingIntent.SUBSTITUTE:
        return SessionDecision(SessionAction.PROPOSE_SUBSTITUTE, "holiday substitution requested")
    return SessionDecision(SessionAction.PRESENT_ORIGINAL_AWAY, "normal training is accessible while away")


def _validate_days(days: frozenset[int] | None) -> None:
    if days is not None and any(isinstance(day, bool) or not isinstance(day, int) or day not in range(7) for day in days):
        raise ValueError("available training days use Monday=0 through Sunday=6")
