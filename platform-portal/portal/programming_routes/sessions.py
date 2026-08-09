from flask import Blueprint, abort, redirect, render_template, request, url_for

from ..extensions import db
from ..models.programming import TrainingSession, TrainingWeek
from ..programming_services.sessions import (
    create,
    delete,
    duplicate,
    insert_blank,
)
from ..programming_templates import day_templates
from ..services.weekly_programming_intelligence import map_athlete_programming_context
from ..models.warmup import WarmupAssignment, WarmupProtocol
from ..services.persisted_warmups import resolve_warmup


def _redirect_after_edit(session: TrainingSession):
    if request.form.get("week_editor"):
        return redirect(
            url_for(
                "programming.week",
                week_id=session.week_id,
                _anchor=f"session-{session.id}",
            )
        )
    return redirect(url_for("programming.session", session_id=session.id))


def register_session_routes(blueprint: Blueprint) -> None:
    @blueprint.post("/programming/weeks/<int:week_id>/sessions")
    def create_session(week_id: int):
        week = db.session.get(TrainingWeek, week_id)
        if week is None:
            abort(404)
        session = create(
            week,
            name=request.form.get("name", "").strip(),
            day_label=request.form.get("day_label", "").strip() or None,
        )
        return _redirect_after_edit(session)

    @blueprint.post("/programming/sessions/<int:session_id>/insert-before")
    def insert_session_before(session_id: int):
        source = db.session.get(TrainingSession, session_id)
        if source is None:
            abort(404)
        target = insert_blank(source, after=False)
        return _redirect_after_edit(target)

    @blueprint.post("/programming/sessions/<int:session_id>/insert-after")
    def insert_session_after(session_id: int):
        source = db.session.get(TrainingSession, session_id)
        if source is None:
            abort(404)
        target = insert_blank(source, after=True)
        return _redirect_after_edit(target)

    @blueprint.get("/programming/sessions/<int:session_id>")
    def session(session_id: int):
        item = db.session.get(TrainingSession, session_id)
        if item is None:
            abort(404)
        week = item.week
        block = week.block
        return render_template(
            "programming/session.html",
            session=item,
            week=week,
            block=block,
            day_templates=day_templates(),
            athlete_context=map_athlete_programming_context(block.athlete),
            warmup_steps=resolve_warmup(block.athlete_id, item.id),
            warmup_assignments=WarmupAssignment.query.filter_by(session_id=item.id).all(),
            warmup_protocols=WarmupProtocol.query.order_by(WarmupProtocol.name, WarmupProtocol.version.desc()).all(),
        )

    @blueprint.post("/programming/sessions/<int:session_id>/duplicate")
    def duplicate_session(session_id: int):
        source = db.session.get(TrainingSession, session_id)
        if source is None:
            abort(404)
        target = duplicate(source)
        return _redirect_after_edit(target)

    @blueprint.post("/programming/sessions/<int:session_id>/delete")
    def delete_session(session_id: int):
        item = db.session.get(TrainingSession, session_id)
        if item is None:
            abort(404)
        week_id = delete(item)
        return redirect(url_for("programming.week", week_id=week_id))
