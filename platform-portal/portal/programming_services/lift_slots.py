from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models.exercise_library import Exercise
from ..models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingSession,
)
from .revisions import append_revision


def _validate_exercise(exercise: Exercise, lift_family: str, role: str) -> None:
    if exercise.lift_family != lift_family:
        raise ValueError(
            f"{role} exercise must belong to the {lift_family} lift family"
        )


def create(
    session: TrainingSession,
    *,
    lift_family: str,
    top_exercise: Exercise,
    top_sets: int,
    top_reps: str,
    top_rpe: float | None = None,
    top_rpe_min: float | None = None,
    top_rpe_max: float | None = None,
    top_load_kg: float | None = None,
    back_off_exercise: Exercise | None = None,
    back_off_sets: int | None = None,
    back_off_reps: str | None = None,
    back_off_rpe: float | None = None,
    back_off_rpe_min: float | None = None,
    back_off_rpe_max: float | None = None,
    back_off_load_kg: float | None = None,
    provenance: str = "coach_authored",
) -> ProgrammingLiftSlot:
    """Create one exposure with a required top set and optional back-off row."""
    _validate_exercise(top_exercise, lift_family, "top-set")
    if back_off_exercise is None and back_off_sets is not None:
        back_off_exercise = top_exercise
    if back_off_exercise is not None:
        _validate_exercise(back_off_exercise, lift_family, "back-off")
        if back_off_sets is None or not back_off_reps:
            raise ValueError("back-off requires sets and reps")

    prescription_position = len(session.prescriptions) + 1
    slot = ProgrammingLiftSlot(
        session=session,
        position=len(session.lift_slots) + 1,
        lift_family=lift_family,
    )
    db.session.add(slot)
    rows = [
        ExercisePrescription(
            session=session,
            exercise=top_exercise,
            exercise_name=top_exercise.name,
            position=prescription_position,
            lift_slot=slot,
            slot_role="top_set",
            provenance=provenance,
            prescription_type="rpe",
            sets=top_sets,
            reps=top_reps,
            load_kg=top_load_kg,
            rpe=top_rpe,
            rpe_min=top_rpe_min,
            rpe_max=top_rpe_max,
        )
    ]
    if back_off_exercise is not None:
        rows.append(
            ExercisePrescription(
                session=session,
                exercise=back_off_exercise,
                exercise_name=back_off_exercise.name,
                position=prescription_position + 1,
                lift_slot=slot,
                slot_role="back_off",
                provenance=provenance,
                prescription_type="rpe",
                sets=back_off_sets,
                reps=back_off_reps,
                load_kg=back_off_load_kg,
                rpe=back_off_rpe,
                rpe_min=back_off_rpe_min,
                rpe_max=back_off_rpe_max,
            )
        )
    db.session.add_all(rows)
    return slot


def _text(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _number(value: str | None, cast):
    return cast(value) if _text(value) is not None else None


def _rpe_values(form: Mapping[str, str], prefix: str) -> dict[str, float | None]:
    mode = form.get(f"{prefix}_rpe_mode", "target")
    if mode == "range":
        return {
            "rpe": None,
            "rpe_min": _number(form.get(f"{prefix}_rpe_min"), float),
            "rpe_max": _number(form.get(f"{prefix}_rpe_max"), float),
        }
    return {
        "rpe": _number(form.get(f"{prefix}_rpe"), float),
        "rpe_min": None,
        "rpe_max": None,
    }


def save_from_form(
    session: TrainingSession,
    form: Mapping[str, str],
    *,
    slot: ProgrammingLiftSlot | None = None,
) -> ProgrammingLiftSlot:
    """Create or update a complete lift slot from the coach editor."""
    family = _text(form.get("lift_family"))
    if family not in {"squat", "bench", "deadlift"}:
        raise ValueError("a valid lift family is required")
    top_exercise = db.session.get(Exercise, _number(form.get("top_exercise_id"), int))
    if top_exercise is None:
        raise ValueError("a catalogue top-set exercise is required")
    _validate_exercise(top_exercise, family, "top-set")

    top_values = {
        "sets": _number(form.get("top_sets"), int),
        "reps": _text(form.get("top_reps")),
        "load_kg": _number(form.get("top_load_kg"), float),
        **_rpe_values(form, "top"),
    }
    if top_values["sets"] is None or not top_values["reps"]:
        raise ValueError("top set requires sets and reps")

    back_enabled = form.get("back_off_enabled") in {"1", "true", "on"}
    back_exercise = None
    back_values: dict[str, object] = {}
    if back_enabled:
        back_id = _number(form.get("back_off_exercise_id"), int)
        back_exercise = top_exercise if back_id is None else db.session.get(Exercise, back_id)
        if back_exercise is None:
            raise ValueError("a catalogue back-off exercise is required")
        _validate_exercise(back_exercise, family, "back-off")
        back_values = {
            "sets": _number(form.get("back_off_sets"), int),
            "reps": _text(form.get("back_off_reps")),
            "load_kg": _number(form.get("back_off_load_kg"), float),
            **_rpe_values(form, "back_off"),
        }
        if back_values["sets"] is None or not back_values["reps"]:
            raise ValueError("back-off requires sets and reps")

    try:
        if slot is None:
            slot = ProgrammingLiftSlot(
                session=session,
                position=len(session.lift_slots) + 1,
                lift_family=family,
            )
            db.session.add(slot)
        elif slot.session_id != session.id:
            raise ValueError("lift slot does not belong to this session")
        slot.lift_family = family

        rows = {row.slot_role: row for row in slot.prescriptions}
        top = rows.get("top_set")
        if top is None:
            top = ExercisePrescription(
                session=session,
                lift_slot=slot,
                slot_role="top_set",
                position=len(session.prescriptions) + 1,
            )
            db.session.add(top)
        top.exercise = top_exercise
        top.exercise_name = top_exercise.name
        top.provenance = "coach_authored"
        top.prescription_type = "rpe"
        for name, value in top_values.items():
            setattr(top, name, value)

        back = rows.get("back_off")
        if back_enabled:
            if back is None:
                back = ExercisePrescription(
                    session=session,
                    lift_slot=slot,
                    slot_role="back_off",
                    position=len(session.prescriptions) + 2,
                )
                db.session.add(back)
            back.exercise = back_exercise
            back.exercise_name = back_exercise.name
            back.provenance = "coach_authored"
            back.prescription_type = "rpe"
            for name, value in back_values.items():
                setattr(back, name, value)
        elif back is not None:
            db.session.delete(back)
        append_revision(session.week.block, change_type="lift_slot_saved", summary=f'Saved {family} lift slot')
        db.session.commit()
    except (SQLAlchemyError, TypeError, ValueError):
        db.session.rollback()
        raise
    return slot


def delete(slot: ProgrammingLiftSlot) -> None:
    try:
        for row in list(slot.prescriptions):
            db.session.delete(row)
        db.session.delete(slot)
        db.session.flush()
        for position, item in enumerate(slot.session.lift_slots, start=1):
            item.position = position
        session = slot.session
        append_revision(session.week.block, change_type="lift_slot_deleted", summary=f'Deleted {slot.lift_family} lift slot')
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise
