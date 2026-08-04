from __future__ import annotations

from dataclasses import dataclass

from ..models.meet_day import Meet, MeetLift

LIFT_ORDER = {"squat": 0, "bench": 1, "deadlift": 2}


@dataclass(frozen=True)
class MeetDayBoard:
    meet: Meet
    next_lift: MeetLift | None
    next_by_entry: dict[int, MeetLift | None]


def _attempt_key(item: MeetLift) -> tuple[int, int, int, int]:
    entry = item.entry
    return (LIFT_ORDER[item.lift], entry.flight, item.sequence, entry.platform_order)


def build_board(meet: Meet) -> MeetDayBoard:
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
    )
