from flask import Blueprint, abort, redirect, request, url_for

from ..extensions import db
from ..models.programming import ExercisePrescription, TrainingSession
from ..programming_services.prescriptions import create, delete, update
from ..tenancy import require_programming_access
from ..programming_services.conflicts import require_editable


def _redirect_to_editor(session: TrainingSession):
    if request.form.get("week_editor"):
        return redirect(
            url_for(
                "programming.week",
                week_id=session.week_id,
                _anchor=f"session-{session.id}",
            )
        )
    return redirect(url_for("programming.session", session_id=session.id))


def register_prescription_routes(blueprint: Blueprint) -> None:
    @blueprint.post("/programming/sessions/<int:session_id>/prescriptions")
    def create_prescription(session_id: int):
        session = db.session.get(TrainingSession, session_id)
        if session is None:
            abort(404)
        require_programming_access(session)
        try:
            require_editable(session.week.block)
        except ValueError as error:
            abort(409, description=str(error))
        name = request.form.get("exercise_name", "").strip()
        if not name:
            abort(400)
        try:
            create(session, name=name, form=request.form)
        except ValueError:
            abort(400)
        return _redirect_to_editor(session)

    @blueprint.post("/programming/prescriptions/<int:prescription_id>")
    def update_prescription(prescription_id: int):
        item = db.session.get(ExercisePrescription, prescription_id)
        if item is None:
            abort(404)
        require_programming_access(item.session)
        try:
            require_editable(item.session.week.block)
        except ValueError as error:
            abort(409, description=str(error))
        if item.lift_slot_id is not None:
            abort(409, description="Edit main lifts through the lift-slot editor.")
        name = request.form.get("exercise_name", "").strip()
        if not name:
            abort(400)
        try:
            update(item, name=name, form=request.form)
        except ValueError:
            abort(400)
        return _redirect_to_editor(item.session)

    @blueprint.post("/programming/prescriptions/<int:prescription_id>/delete")
    def delete_prescription(prescription_id: int):
        item = db.session.get(ExercisePrescription, prescription_id)
        if item is None:
            abort(404)
        require_programming_access(item.session)
        try:
            require_editable(item.session.week.block)
        except ValueError as error:
            abort(409, description=str(error))
        if item.lift_slot_id is not None:
            abort(409, description="Remove main lifts through the lift-slot editor.")
        session = item.session
        delete(item)
        return _redirect_to_editor(session)
