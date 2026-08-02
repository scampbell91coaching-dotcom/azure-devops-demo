from flask import Blueprint, abort, redirect, request, url_for

from ..extensions import db
from ..models.programming import TrainingSession
from ..programming_services.prescriptions import create


def register_prescription_routes(blueprint: Blueprint) -> None:
    @blueprint.post("/programming/sessions/<int:session_id>/prescriptions")
    def create_prescription(session_id: int):
        session = db.session.get(TrainingSession, session_id)
        if session is None:
            abort(404)
        name = request.form.get("exercise_name", "").strip()
        if not name:
            abort(400)
        create(session, name=name, form=request.form)
        return redirect(url_for("programming.session", session_id=session.id))
