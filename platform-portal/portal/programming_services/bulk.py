from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models.programming import ExercisePrescription, TrainingBlock, TrainingWeek
from .revisions import append_revision

FIELDS = {"sets", "reps", "rpe", "load_kg", "percentage"}


@dataclass(frozen=True)
class BulkChange:
    prescription_id: int
    location: str
    field: str
    old: object
    new: object


def preview(block: TrainingBlock, week_ids: set[int], field: str, value: str) -> list[BulkChange]:
    if field not in FIELDS or not week_ids:
        raise ValueError("Choose at least one week and a supported field.")
    parsed: object = value.strip()
    if field == "sets":
        parsed = int(value)
        if parsed < 1:
            raise ValueError("Sets must be at least one.")
    elif field in {"rpe", "load_kg", "percentage"}:
        parsed = float(value)
        if field == "rpe" and not 1 <= parsed <= 10:
            raise ValueError("RPE must be between 1 and 10.")
        if field != "rpe" and parsed < 0:
            raise ValueError("Load and percentage cannot be negative.")
    elif not parsed:
        raise ValueError("Reps cannot be blank.")
    changes = []
    for week in block.weeks:
        if week.id not in week_ids:
            continue
        for session in week.sessions:
            for item in session.prescriptions:
                old = getattr(item, field)
                if old != parsed:
                    changes.append(BulkChange(item.id, f"Week {week.position} · {session.name} · {item.exercise_name}", field, old, parsed))
    return changes


def apply(block: TrainingBlock, changes: list[BulkChange], *, reason: str) -> None:
    if not reason.strip() or not changes:
        raise ValueError("A reason and at least one change are required.")
    try:
        rows = {row.id: row for row in ExercisePrescription.query.filter(
            ExercisePrescription.id.in_([change.prescription_id for change in changes])).all()}
        for change in changes:
            row = rows.get(change.prescription_id)
            if row is None or row.session.week.block_id != block.id:
                raise ValueError("Bulk scope changed; preview again.")
            setattr(row, change.field, change.new)
            row.provenance = "coach_authored"
        append_revision(block, change_type="bulk_progression", summary=f"Bulk adjusted {len(changes)} prescriptions", reason=reason)
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        raise
