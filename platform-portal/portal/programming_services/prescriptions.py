from collections.abc import Mapping
from typing import cast

from ..extensions import db
from ..models.programming import ExercisePrescription, TrainingSession


def _float(value: str | None) -> float | None:
    return float(value) if value and value.strip() else None


def _int(value: str | None) -> int | None:
    return int(value) if value and value.strip() else None


def copy(source: TrainingSession, target: TrainingSession) -> None:
    for item in cast(list[ExercisePrescription], source.prescriptions):
        db.session.add(ExercisePrescription(session=target, **item.copy_values()))


def create(
    session: TrainingSession,
    *,
    name: str,
    form: Mapping[str, str],
) -> ExercisePrescription:
    item = ExercisePrescription(
        session=session,
        exercise_name=name,
        position=len(session.prescriptions) + 1,
        sets=_int(form.get("sets")),
        reps=(form.get("reps") or "").strip() or None,
        load_kg=_float(form.get("load_kg")),
        percentage=_float(form.get("percentage")),
        rpe=_float(form.get("rpe")),
        tempo=(form.get("tempo") or "").strip() or None,
        rest_seconds=_int(form.get("rest_seconds")),
        notes=(form.get("notes") or "").strip() or None,
    )
    db.session.add(item)
    db.session.commit()
    return item
