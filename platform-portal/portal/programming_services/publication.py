from __future__ import annotations

from collections import Counter

from ..models.programming import TrainingBlock


def publication_blockers(block: TrainingBlock) -> list[str]:
    """Return coach-readable violations of existing graph/model invariants."""
    blockers: list[str] = []
    if not block.weeks:
        blockers.append("Add at least one week before publishing.")
    week_positions = Counter(week.position for week in block.weeks)
    for week in block.weeks:
        label = f'Week {week.position} ("{week.name}")'
        if week.position is None or week.position <= 0:
            blockers.append(f"{label} needs a valid position.")
        if week_positions[week.position] > 1:
            blockers.append(f"{label} has a duplicate week position.")
        if not week.sessions:
            blockers.append(f"{label} needs at least one session.")
        session_positions = Counter(session.position for session in week.sessions)
        for session in week.sessions:
            session_label = f'{label}, session {session.position} ("{session.name}")'
            if session.position is None or session.position <= 0:
                blockers.append(f"{session_label} needs a valid position.")
            if session_positions[session.position] > 1:
                blockers.append(f"{session_label} has a duplicate session position.")
            if not session.prescriptions:
                blockers.append(f"{session_label} needs programmed exercises.")
            prescription_positions = Counter(row.position for row in session.prescriptions)
            for row in session.prescriptions:
                if row.position is None or row.position <= 0:
                    blockers.append(f'{session_label}, "{row.exercise_name}" needs a valid position.')
                if prescription_positions[row.position] > 1:
                    blockers.append(f"{session_label} has duplicate exercise positions.")
                try:
                    row.validate()
                except ValueError as error:
                    blockers.append(f'{session_label}, "{row.exercise_name}": {error}.')
            slot_positions = Counter(slot.position for slot in session.lift_slots)
            for slot in session.lift_slots:
                if slot_positions[slot.position] > 1:
                    blockers.append(f"{session_label} has duplicate lift-slot positions.")
                roles = Counter(row.slot_role for row in slot.prescriptions)
                if roles["top_set"] != 1:
                    blockers.append(f"{session_label}, {slot.lift_family} needs exactly one top set.")
                if any(row.exercise_id is None or row.exercise is None for row in slot.prescriptions):
                    blockers.append(f"{session_label}, {slot.lift_family} references a missing exercise.")
    return list(dict.fromkeys(blockers))
