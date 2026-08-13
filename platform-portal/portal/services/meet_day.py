from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..models.meet_day import Meet, MeetLift
from .competition_day import unpack_notes

LIFT_ORDER = {"squat": 0, "bench": 1, "deadlift": 2}


@dataclass(frozen=True)
class MeetDayBoard:
    meet: Meet
    next_lift: MeetLift | None
    next_by_entry: dict[int, MeetLift | None]
    meet_notes: str | None
    meet_workflow: dict
    entry_notes: dict[int, str | None]
    entry_workflow: dict[int, dict]
    lift_notes: dict[int, str | None]
    lift_workflow: dict[int, dict]
    days_until_meet: int
    timeline_label: str
    missing_context: tuple[str, ...]
    total_attempts: int
    entry_readiness: dict[int, str]


def _attempt_key(item: MeetLift) -> tuple[int, int, int, int]:
    entry = item.entry
    return (LIFT_ORDER[item.lift], entry.flight, item.sequence, entry.platform_order)


def _timeline_label(days_until_meet: int) -> str:
    if days_until_meet == 0:
        return "Meet day"
    if days_until_meet > 0:
        return f"D-{days_until_meet}"
    days_ago = abs(days_until_meet)
    return f"{days_ago} day{'s' if days_ago != 1 else ''} ago"


def _entry_readiness(entry) -> str:
    attempts = [item for item in entry.lifts if item.kind == "attempt"]
    if not attempts:
        return "Attempt plan not started"
    pending = [item for item in attempts if item.outcome == "pending"]
    if not pending:
        return "All planned attempts resolved"
    opener_lifts = {item.lift for item in attempts if item.sequence == 1 and item.weight_kg}
    missing_openers = [lift.title() for lift in LIFT_ORDER if lift not in opener_lifts]
    if missing_openers:
        return f"Missing {' / '.join(missing_openers)} opener"
    return f"Openers set · {len(attempts)} attempt{'s' if len(attempts) != 1 else ''} planned"


def build_board(meet: Meet, *, today: date | None = None) -> MeetDayBoard:
    meet_notes, meet_workflow = unpack_notes(meet.notes)
    entry_payloads = {entry.id: unpack_notes(entry.notes) for entry in meet.entries}
    lift_payloads = {
        item.id: unpack_notes(item.notes)
        for entry in meet.entries
        for item in entry.lifts
    }
    pending = [
        item
        for entry in meet.entries
        for item in entry.lifts
        if item.kind == "attempt" and item.outcome == "pending"
    ]
    pending.sort(key=_attempt_key)
    attempts = [
        item
        for entry in meet.entries
        for item in entry.lifts
        if item.kind == "attempt"
    ]
    days_until_meet = (meet.meet_date - (today or date.today())).days
    missing_context = tuple(
        label
        for value, label in (
            (meet.federation, "federation"),
            (meet.weight_class, "weight class"),
            (meet.bodyweight_kg, "official bodyweight"),
        )
        if value in (None, "")
    )
    next_by_entry = {
        entry.id: next(
            (
                item
                for item in sorted(
                    entry.lifts, key=lambda lift: (LIFT_ORDER[lift.lift], lift.sequence)
                )
                if item.kind == "attempt" and item.outcome == "pending"
            ),
            None,
        )
        for entry in meet.entries
    }
    return MeetDayBoard(
        meet=meet,
        next_lift=pending[0] if pending else None,
        next_by_entry=next_by_entry,
        meet_notes=meet_notes,
        meet_workflow=meet_workflow,
        entry_notes={key: value[0] for key, value in entry_payloads.items()},
        entry_workflow={key: value[1] for key, value in entry_payloads.items()},
        lift_notes={key: value[0] for key, value in lift_payloads.items()},
        lift_workflow={key: value[1] for key, value in lift_payloads.items()},
        days_until_meet=days_until_meet,
        timeline_label=_timeline_label(days_until_meet),
        missing_context=missing_context,
        total_attempts=len(attempts),
        entry_readiness={entry.id: _entry_readiness(entry) for entry in meet.entries},
    )
