from __future__ import annotations

from ..extensions import db
from ..models.exercise_library import Exercise
from ..models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingSession,
)


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
