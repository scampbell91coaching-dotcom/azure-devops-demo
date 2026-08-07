from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models.programming import (
    ExercisePrescription,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
)

_ROW_PATTERN = re.compile(r"^row-(\d+)-(\d+)$")
MAX_EXTRA_SETS = 5
MAX_LOAD_KG = 1000
MAX_REPS = 1000
MAX_NOTE_LENGTH = 500


@dataclass(frozen=True)
class SaveResult:
    log: TrainingSessionLog | None
    errors: tuple[str, ...]


def assigned_log(athlete_id: int, session_id: int) -> TrainingSessionLog | None:
    return TrainingSessionLog.query.filter_by(
        athlete_id=athlete_id, session_id=session_id
    ).one_or_none()


def save_training_session(
    training_session: TrainingSession,
    athlete_id: int,
    form: Mapping[str, str],
) -> SaveResult:
    """Validate and idempotently upsert submitted working sets."""
    log = assigned_log(athlete_id, training_session.id)
    if log is not None and log.status == "completed":
        return SaveResult(log, ("Completed sessions are read-only.",))

    prescriptions = {item.id: item for item in training_session.prescriptions}
    parsed: list[tuple[ExercisePrescription, int, dict[str, object]]] = []
    errors: list[str] = []
    seen: set[tuple[int, int]] = set()

    for key in form:
        match = _ROW_PATTERN.match(key)
        if not match:
            continue
        prescription_id, set_order = (int(value) for value in match.groups())
        prescription = prescriptions.get(prescription_id)
        if prescription is None:
            errors.append("An exercise in this submission is not part of the session.")
            continue
        identity = (prescription_id, set_order)
        if identity in seen:
            continue
        seen.add(identity)
        prescribed_sets = prescription.sets or 1
        if set_order < 1 or set_order > prescribed_sets + MAX_EXTRA_SETS:
            errors.append(f"Set number for {prescription.exercise_name} is invalid.")
            continue

        prefix = f"set-{prescription_id}-{set_order}"
        completed = form.get(f"{prefix}-completed") == "1"
        skipped = form.get(f"{prefix}-skipped") == "1"
        if completed and skipped:
            errors.append(
                f"{prescription.exercise_name} set {set_order} cannot be completed and skipped."
            )
        values = {
            "completed": completed,
            "skipped": skipped,
            "actual_load_kg": _number(
                form.get(f"{prefix}-load"), "Load", 0, MAX_LOAD_KG, errors
            ),
            "actual_reps": _number(
                form.get(f"{prefix}-reps"),
                "Reps",
                0,
                MAX_REPS,
                errors,
                integer=True,
            ),
            "actual_rpe": _number(form.get(f"{prefix}-rpe"), "RPE", 1, 10, errors),
            "athlete_note": (form.get(f"{prefix}-note") or "").strip() or None,
        }
        note = values["athlete_note"]
        if isinstance(note, str) and len(note) > MAX_NOTE_LENGTH:
            errors.append(f"Notes must be {MAX_NOTE_LENGTH} characters or fewer.")
        if completed and values["actual_reps"] is None:
            errors.append(
                f"Enter reps for completed {prescription.exercise_name} set {set_order}."
            )
        if skipped and any(
            values[name] is not None
            for name in ("actual_load_kg", "actual_reps", "actual_rpe")
        ):
            errors.append(
                f"Skipped {prescription.exercise_name} set {set_order} cannot have results."
            )
        if (
            completed
            or skipped
            or any(
                values[name] is not None
                for name in (
                    "actual_load_kg",
                    "actual_reps",
                    "actual_rpe",
                    "athlete_note",
                )
            )
        ):
            parsed.append((prescription, set_order, values))

    if errors:
        return SaveResult(log, tuple(dict.fromkeys(errors)))

    intent = form.get("intent", "save")
    if intent not in {"save", "finish"}:
        return SaveResult(log, ("Unknown session action.",))
    if not parsed and log is None:
        return SaveResult(None, ("Record at least one set before saving.",))

    if log is None:
        log = TrainingSessionLog(
            athlete_id=athlete_id,
            session_id=training_session.id,
            session_name=training_session.name,
            block_name=training_session.week.block.name,
            week_name=training_session.week.name,
            status="in_progress",
        )
        db.session.add(log)
        db.session.flush()

    existing = {(item.exercise_position, item.set_order): item for item in log.results}
    for prescription, set_order, values in parsed:
        identity = (prescription.position, set_order)
        result = existing.get(identity)
        if result is None:
            result = TrainingSetResult(
                session_log=log,
                prescription_id=prescription.id,
                exercise_name=prescription.exercise_name,
                exercise_position=prescription.position,
                set_order=set_order,
                is_extra=set_order > (prescription.sets or 1),
                prescribed_reps=_prescribed_reps(prescription),
                prescribed_load_kg=(
                    prescription.load_kg
                    if prescription.load_kg is not None
                    else prescription.target_load_kg or prescription.load_cap_kg
                ),
                prescribed_rpe=(
                    prescription.rpe
                    if prescription.rpe is not None
                    else prescription.target_rpe or prescription.rpe_cap
                ),
            )
            db.session.add(result)
            existing[identity] = result
        for name, value in values.items():
            setattr(result, name, value)

    if intent == "finish":
        missing = []
        for prescription in training_session.prescriptions:
            for set_order in range(1, (prescription.sets or 1) + 1):
                result = existing.get((prescription.position, set_order))
                if result is None or not (result.completed or result.skipped):
                    missing.append(f"{prescription.exercise_name} set {set_order}")
        if missing:
            db.session.rollback()
            current = assigned_log(athlete_id, training_session.id)
            return SaveResult(
                current,
                (
                    "Complete or skip every prescribed set before finishing: "
                    + ", ".join(missing),
                ),
            )
        log.status = "completed"
        log.completed_at = datetime.now(UTC)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # A repeated concurrent first POST resolves to the already-created log.
        current = assigned_log(athlete_id, training_session.id)
        return SaveResult(current, ("The session changed; reload and try again.",))
    return SaveResult(log, ())


def _number(
    raw: str | None,
    label: str,
    minimum: float,
    maximum: float,
    errors: list[str],
    *,
    integer: bool = False,
) -> float | int | None:
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw) if integer else float(raw)
    except (TypeError, ValueError):
        errors.append(f"{label} must be a number.")
        return None
    if value < minimum or value > maximum:
        errors.append(f"{label} must be between {minimum:g} and {maximum:g}.")
        return None
    return value


def _prescribed_reps(item: ExercisePrescription) -> str | None:
    if item.reps:
        return item.reps
    if item.reps_min is not None and item.reps_max is not None:
        return f"{item.reps_min}-{item.reps_max}"
    if item.target_reps is not None:
        return str(item.target_reps)
    return None
