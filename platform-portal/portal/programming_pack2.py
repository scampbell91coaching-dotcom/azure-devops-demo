from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from .extensions import db
from .models.programming import ExercisePrescription, TrainingSession
from .models.exercise_library import Exercise

programming_pack2_bp = Blueprint("programming_pack2", __name__)


def _optional_float(value):
    if value in (None, ""):
        return None
    return float(value)


def _optional_int(value):
    if value in (None, ""):
        return None
    return int(value)


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

    payload = request.get_json(silent=True) or {}
    exercise_name = str(payload.get("exercise_name", "")).strip()

    if not exercise_name:
        return jsonify({"error": "Exercise name is required."}), 400

    item = ExercisePrescription(
        session=session,
        exercise_name=exercise_name,
        position=len(session.prescriptions) + 1,
        provenance="coach_authored",
        sets=_optional_int(payload.get("sets")),
        reps=str(payload.get("reps", "")).strip() or None,
        load_kg=_optional_float(payload.get("load_kg")),
        percentage=_optional_float(payload.get("percentage")),
        rpe=_optional_float(payload.get("rpe")),
        tempo=str(payload.get("tempo", "")).strip() or None,
        rest_seconds=_optional_int(payload.get("rest_seconds")),
        notes=str(payload.get("notes", "")).strip() or None,
    )

    db.session.add(item)
    db.session.commit()

    return jsonify(_serialize(item)), 201


@programming_pack2_bp.patch("/programming/api/prescriptions/<int:prescription_id>")
def update_prescription(prescription_id: int):
    item = db.session.get(ExercisePrescription, prescription_id)

    if item is None:
        abort(404)
    if item.lift_slot_id is not None:
        return jsonify({"error": "Edit main lifts through the lift-slot editor."}), 409

    payload = request.get_json(silent=True) or {}

    if "exercise_name" in payload:
        name = str(payload["exercise_name"]).strip()
        if not name:
            return jsonify({"error": "Exercise name is required."}), 400
        item.exercise_name = name

    if "sets" in payload:
        item.sets = _optional_int(payload["sets"])
    if "reps" in payload:
        item.reps = str(payload["reps"]).strip() or None
    if "load_kg" in payload:
        item.load_kg = _optional_float(payload["load_kg"])
    if "percentage" in payload:
        item.percentage = _optional_float(payload["percentage"])
    if "rpe" in payload:
        item.rpe = _optional_float(payload["rpe"])
    if "tempo" in payload:
        item.tempo = str(payload["tempo"]).strip() or None
    if "rest_seconds" in payload:
        item.rest_seconds = _optional_int(payload["rest_seconds"])
    if "notes" in payload:
        item.notes = str(payload["notes"]).strip() or None

    db.session.commit()
    return jsonify(_serialize(item))


@programming_pack2_bp.delete("/programming/api/prescriptions/<int:prescription_id>")
def delete_prescription(prescription_id: int):
    item = db.session.get(ExercisePrescription, prescription_id)

    if item is None:
        abort(404)
    if item.lift_slot_id is not None:
        return jsonify({"error": "Remove main lifts through the lift-slot editor."}), 409

    session = item.session
    db.session.delete(item)
    db.session.flush()

    for position, prescription in enumerate(session.prescriptions, start=1):
        prescription.position = position

    db.session.commit()
    return "", 204


@programming_pack2_bp.post("/programming/api/sessions/<int:session_id>/reorder")
def reorder_prescriptions(session_id: int):
    session = db.session.get(TrainingSession, session_id)

    if session is None:
        abort(404)

    payload = request.get_json(silent=True) or {}
    ids = payload.get("prescription_ids", [])

    by_id = {
        item.id: item for item in session.prescriptions if item.lift_slot_id is None
    }

    if not isinstance(ids, list) or set(ids) != set(by_id):
        return jsonify({"error": "Invalid prescription order."}), 400

    first_assistance_position = 1 + sum(
        len(slot.prescriptions) for slot in session.lift_slots
    )
    for position, prescription_id in enumerate(ids, start=first_assistance_position):
        by_id[prescription_id].position = position

    db.session.commit()
    return jsonify({"status": "saved"})
