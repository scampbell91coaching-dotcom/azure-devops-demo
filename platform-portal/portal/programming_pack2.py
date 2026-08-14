from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from .extensions import db
from .models.programming import ExercisePrescription, TrainingSession
from .models.exercise_library import Exercise
from .programming_services.revisions import append_revision
from .programming_validation import (
    optional_float,
    optional_int,
    optional_string,
    require_json_object,
)
from .tenancy import require_programming_access

programming_pack2_bp = Blueprint("programming_pack2", __name__)


FIELDS = frozenset({
    "exercise_name", "sets", "reps", "load_kg", "percentage", "rpe",
    "tempo", "rest_seconds", "notes",
})


def _values(payload):
    return {
        "sets": optional_int(payload.get("sets"), field="sets", minimum=1, maximum=100),
        "reps": optional_string(payload.get("reps"), field="reps", maximum=80),
        "load_kg": optional_float(payload.get("load_kg"), field="load_kg", minimum=0, maximum=2000),
        "percentage": optional_float(payload.get("percentage"), field="percentage", minimum=0, maximum=100),
        "rpe": optional_float(payload.get("rpe"), field="rpe", minimum=0, maximum=10),
        "tempo": optional_string(payload.get("tempo"), field="tempo", maximum=40),
        "rest_seconds": optional_int(payload.get("rest_seconds"), field="rest_seconds", minimum=0, maximum=7200),
        "notes": optional_string(payload.get("notes"), field="notes", maximum=2000),
    }


def _serialize(item):
    return {
        "id": item.id,
        "exercise_name": item.exercise_name,
        "sets": item.sets,
        "reps": item.reps,
        "load_kg": item.load_kg,
        "percentage": item.percentage,
        "rpe": item.rpe,
        "tempo": item.tempo,
        "rest_seconds": item.rest_seconds,
        "notes": item.notes,
    }


@programming_pack2_bp.get("/programming/api/exercises")
def exercise_suggestions():
    query = request.args.get("q", "").strip().lower()

    catalogue = Exercise.query.filter_by(active=True)
    if query:
        catalogue = catalogue.filter(Exercise.name.ilike(f"%{query}%"))
    names = [item.name for item in catalogue.order_by(Exercise.name.asc()).limit(40)]

    return jsonify(names)


@programming_pack2_bp.post("/programming/api/sessions/<int:session_id>/prescriptions")
def create_prescription(session_id: int):
    session = db.session.get(TrainingSession, session_id)

    if session is None:
        abort(404)
    require_programming_access(session)

    payload = require_json_object(allowed_keys=FIELDS)
    exercise_name = optional_string(payload.get("exercise_name"), field="exercise_name", maximum=160, allow_empty=False)
    values = _values(payload)

    item = ExercisePrescription(
        session=session,
        exercise_name=exercise_name,
        position=len(session.prescriptions) + 1,
        provenance="coach_authored",
        **values,
    )

    db.session.add(item)
    append_revision(session.week.block, change_type="prescription_created", summary=f'Added prescription "{exercise_name}"')
    db.session.commit()

    return jsonify(_serialize(item)), 201


@programming_pack2_bp.patch("/programming/api/prescriptions/<int:prescription_id>")
def update_prescription(prescription_id: int):
    item = db.session.get(ExercisePrescription, prescription_id)

    if item is None:
        abort(404)
    require_programming_access(item.session)
    if item.lift_slot_id is not None:
        return jsonify({"error": "Edit main lifts through the lift-slot editor."}), 409

    payload = require_json_object(allowed_keys=FIELDS)

    if "exercise_name" in payload:
        name = optional_string(payload["exercise_name"], field="exercise_name", maximum=160, allow_empty=False)
        item.exercise_name = name
    values = _values(payload)
    for field in FIELDS - {"exercise_name"}:
        if field in payload:
            setattr(item, field, values[field])

    append_revision(item.session.week.block, change_type="prescription_updated", summary=f'Updated prescription "{item.exercise_name}"')
    db.session.commit()
    return jsonify(_serialize(item))


@programming_pack2_bp.delete("/programming/api/prescriptions/<int:prescription_id>")
def delete_prescription(prescription_id: int):
    item = db.session.get(ExercisePrescription, prescription_id)

    if item is None:
        abort(404)
    require_programming_access(item.session)
    if item.lift_slot_id is not None:
        return jsonify({"error": "Remove main lifts through the lift-slot editor."}), 409

    session = item.session
    db.session.delete(item)
    db.session.flush()

    for position, prescription in enumerate(session.prescriptions, start=1):
        prescription.position = position

    append_revision(session.week.block, change_type="prescription_deleted", summary=f'Deleted prescription "{item.exercise_name}"')
    db.session.commit()
    return "", 204


@programming_pack2_bp.post("/programming/api/sessions/<int:session_id>/reorder")
def reorder_prescriptions(session_id: int):
    session = db.session.get(TrainingSession, session_id)

    if session is None:
        abort(404)
    require_programming_access(session)

    payload = require_json_object(allowed_keys=frozenset({"prescription_ids"}))
    ids = payload.get("prescription_ids", [])

    by_id = {
        item.id: item for item in session.prescriptions if item.lift_slot_id is None
    }

    if (
        not isinstance(ids, list)
        or len(ids) > 500
        or any(not isinstance(item, int) or isinstance(item, bool) for item in ids)
        or len(ids) != len(set(ids))
        or set(ids) != set(by_id)
    ):
        return jsonify({"error": "Invalid prescription order."}), 400

    first_assistance_position = 1 + sum(
        len(slot.prescriptions) for slot in session.lift_slots
    )
    for position, prescription_id in enumerate(ids, start=first_assistance_position):
        by_id[prescription_id].position = position

    append_revision(session.week.block, change_type="prescriptions_reordered", summary="Reordered assistance prescriptions")
    db.session.commit()
    return jsonify({"status": "saved"})
