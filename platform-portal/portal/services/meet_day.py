from __future__ import annotations

from dataclasses import dataclass

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


def _attempt_key(item: MeetLift) -> tuple[int, int, int, int]:
    entry = item.entry
    return (LIFT_ORDER[item.lift], entry.flight, item.sequence, entry.platform_order)


def build_board(meet: Meet) -> MeetDayBoard:
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
    )
