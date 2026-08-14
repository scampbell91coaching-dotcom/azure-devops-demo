from flask import Blueprint, abort, redirect, request, url_for

from ..extensions import db
from ..models.programming import ProgrammingLiftSlot, TrainingSession
from ..programming_services.lift_slots import delete, save_from_form
from ..tenancy import require_programming_access


def _redirect(session: TrainingSession):
    return redirect(url_for("programming.week", week_id=session.week_id, _anchor=f"session-{session.id}"))


def register_lift_slot_routes(blueprint: Blueprint) -> None:
    @blueprint.post("/programming/sessions/<int:session_id>/lift-slots")
    def create_lift_slot(session_id: int):
        session = db.session.get(TrainingSession, session_id)
        if session is None:
            abort(404)
        require_programming_access(session)
        try:
            save_from_form(session, request.form)
        except (TypeError, ValueError):
            abort(400)
        return _redirect(session)

    @blueprint.post("/programming/lift-slots/<int:slot_id>")
    def update_lift_slot(slot_id: int):
        slot = db.session.get(ProgrammingLiftSlot, slot_id)
        if slot is None:
            abort(404)
        session = slot.session
        require_programming_access(session)
        try:
            save_from_form(session, request.form, slot=slot)
        except (TypeError, ValueError):
            abort(400)
        return _redirect(session)

    @blueprint.post("/programming/lift-slots/<int:slot_id>/delete")
    def delete_lift_slot(slot_id: int):
        slot = db.session.get(ProgrammingLiftSlot, slot_id)
        if slot is None:
            abort(404)
        session = slot.session
        require_programming_access(session)
        delete(slot)
        return _redirect(session)
