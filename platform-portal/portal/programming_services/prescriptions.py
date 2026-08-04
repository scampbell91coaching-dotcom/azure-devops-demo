from collections.abc import Mapping
from typing import cast

from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models.programming import (
    PRESCRIPTION_TYPES,
    ExercisePrescription,
    TrainingSession,
)

PRESCRIPTION_MODE_LABELS = {
    "rpe": "RPE",
    "fixed_load": "Fixed load",
    "load_capped": "Load cap",
    "amrap": "AMRAP",
    "rep_range": "Rep range",
    "single_target": "Target single",
}

_EDITABLE_FIELDS = (
    "sets",
    "reps",
    "reps_min",
    "reps_max",
    "load_kg",
    "load_cap_kg",
    "percentage",
    "rpe",
    "rpe_cap",
    "target_reps",
    "target_rpe",
    "target_load_kg",
    "tempo",
    "rest_seconds",
    "notes",
)


def _text(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _float(value: str | None) -> float | None:
    return float(value) if _text(value) is not None else None


def _int(value: str | None) -> int | None:
    return int(value) if _text(value) is not None else None


def _commit_or_rollback() -> None:
    try:
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        raise


def _values(form: Mapping[str, str]) -> dict[str, object]:
    mode = _text(form.get("prescription_type"))
    if mode is not None and mode not in PRESCRIPTION_TYPES:
        raise ValueError(f"Unknown prescription type: {mode}")
    return {
        "prescription_type": mode,
        "sets": _int(form.get("sets")),
        "reps": _text(form.get("reps")),
        "reps_min": _int(form.get("reps_min")),
        "reps_max": _int(form.get("reps_max")),
        "load_kg": _float(form.get("load_kg")),
        "load_cap_kg": _float(form.get("load_cap_kg")),
        "percentage": _float(form.get("percentage")),
        "rpe": _float(form.get("rpe")),
        "rpe_cap": _float(form.get("rpe_cap")),
        "target_reps": _int(form.get("target_reps")),
        "target_rpe": _float(form.get("target_rpe")),
        "target_load_kg": _float(form.get("target_load_kg")),
        "amrap": mode == "amrap",
        "tempo": _text(form.get("tempo")),
        "rest_seconds": _int(form.get("rest_seconds")),
        "notes": _text(form.get("notes")),
    }


def renumber(
    session: TrainingSession,
    *,
    excluding: ExercisePrescription | None = None,
) -> None:
    prescriptions = sorted(
        (
            item
            for item in cast(list[ExercisePrescription], session.prescriptions)
            if item is not excluding
        ),
        key=lambda item: (item.position, item.id or 0),
    )
    for position, item in enumerate(prescriptions, start=1):
        item.position = position


def copy(source: TrainingSession, target: TrainingSession) -> None:
    for item in cast(list[ExercisePrescription], source.prescriptions):
        db.session.add(ExercisePrescription(session=target, **item.copy_values()))


def create(
    session: TrainingSession,
    *,
    name: str,
    form: Mapping[str, str],
) -> ExercisePrescription:
    renumber(session)
    item = ExercisePrescription(
        session=session,
        exercise_name=name,
        position=len(session.prescriptions) + 1,
        **_values(form),
    )
    db.session.add(item)
    _commit_or_rollback()
    return item


def update(
    item: ExercisePrescription,
    *,
    name: str,
    form: Mapping[str, str],
) -> ExercisePrescription:
    values = _values(form)
    item.exercise_name = name
    # Assign every editable value so switching modes cannot retain stale targets.
    for field in _EDITABLE_FIELDS:
        setattr(item, field, values[field])
    item.prescription_type = cast(str | None, values["prescription_type"])
    item.amrap = cast(bool, values["amrap"])
    _commit_or_rollback()
    return item


def delete(item: ExercisePrescription) -> int:
    session = cast(TrainingSession, item.session)
    session_id = session.id
    try:
        db.session.delete(item)
        renumber(session, excluding=item)
        _commit_or_rollback()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        raise
    return session_id
