from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload, selectinload

from ..extensions import db
from ..models.athlete import Athlete
from ..models.programming import ProgrammingLiftSlot, TrainingBlock, TrainingSession, TrainingWeek
from ..programming_services.sessions import (
    copy_to_week,
    create,
    delete,
    duplicate,
    insert_blank,
    move,
)
from ..programming_templates import day_templates
from ..services.weekly_programming_intelligence import map_athlete_programming_context
from ..models.warmup import WarmupAssignment, WarmupProtocol
from ..services.persisted_warmups import resolve_warmup
from ..services.movement_warmup_candidates import warmup_candidates
from ..tenancy import athlete_query_for_request, require_programming_access
from ..programming_services.conflicts import (
    ActiveProgrammeEditError, ProgrammeConflictError, require_current, require_editable,
)


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
    def check_current(block: TrainingBlock) -> None:
        raw = request.form.get("expected_revision")
        try:
            expected = int(raw) if raw not in (None, "") else None
            require_editable(block)
            require_current(block, expected)
        except ValueError as error:
            if isinstance(error, (ActiveProgrammeEditError, ProgrammeConflictError)):
                abort(409, description=str(error))
            abort(400, description="Invalid programme revision token.")

    @blueprint.post("/programming/weeks/<int:week_id>/sessions")
    def create_session(week_id: int):
        week = db.session.get(TrainingWeek, week_id)
        require_programming_access(week)
        check_current(week.block)
        session = create(
            week,
            name=request.form.get("name", "").strip(),
            day_label=request.form.get("day_label", "").strip() or None,
        )
        return _redirect_after_edit(session)

    @blueprint.post("/programming/sessions/<int:session_id>/insert-before")
    def insert_session_before(session_id: int):
        source = db.session.get(TrainingSession, session_id)
        require_programming_access(source)
        check_current(source.week.block)
        target = insert_blank(source, after=False)
        return _redirect_after_edit(target)

    @blueprint.post("/programming/sessions/<int:session_id>/insert-after")
    def insert_session_after(session_id: int):
        source = db.session.get(TrainingSession, session_id)
        require_programming_access(source)
        check_current(source.week.block)
        target = insert_blank(source, after=True)
        return _redirect_after_edit(target)

    @blueprint.get("/programming/sessions/<int:session_id>")
    def session(session_id: int):
        item = (
            TrainingSession.query.options(
                joinedload(TrainingSession.week)
                .joinedload(TrainingWeek.block)
                .joinedload(TrainingBlock.athlete),
                selectinload(TrainingSession.prescriptions),
                selectinload(TrainingSession.lift_slots).selectinload(
                    ProgrammingLiftSlot.prescriptions
                ),
            )
            .filter_by(id=session_id)
            .one_or_none()
        )
        if item is None:
            abort(404)
        require_programming_access(item)
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
            warmup_candidates=warmup_candidates(block.athlete_id, item),
            workspace_athletes=athlete_query_for_request().order_by(Athlete.last_name.asc()).all(),
        )

    @blueprint.post("/programming/sessions/<int:session_id>/duplicate")
    def duplicate_session(session_id: int):
        source = db.session.get(TrainingSession, session_id)
        require_programming_access(source)
        check_current(source.week.block)
        target = duplicate(source)
        return _redirect_after_edit(target)

    @blueprint.post("/programming/sessions/<int:session_id>/copy-forward-preview")
    def copy_session_forward_preview(session_id: int):
        source = db.session.get(TrainingSession, session_id)
        require_programming_access(source)
        check_current(source.week.block)
        target = db.session.get(TrainingWeek, request.form.get("target_week_id", type=int))
        if target is None or target.block_id != source.week.block_id or target.position <= source.week.position:
            abort(400, description="Choose a later week in this programme.")
        require_programming_access(target)
        return render_template("programming/copy_session_preview.html", source=source, target=target,
            expected_revision=request.form.get("expected_revision", type=int))

    @blueprint.post("/programming/sessions/<int:session_id>/copy-forward")
    def copy_session_forward(session_id: int):
        source = db.session.get(TrainingSession, session_id)
        require_programming_access(source)
        check_current(source.week.block)
        target_week = db.session.get(TrainingWeek, request.form.get("target_week_id", type=int))
        if target_week is None:
            abort(400)
        require_programming_access(target_week)
        try:
            target = copy_to_week(source, target_week)
        except ValueError as error:
            abort(409, description=str(error))
        return redirect(url_for("programming.week", week_id=target_week.id, _anchor=f"session-{target.id}"))

    @blueprint.post("/programming/sessions/<int:session_id>/move")
    def move_session(session_id: int):
        source = db.session.get(TrainingSession, session_id)
        require_programming_access(source)
        check_current(source.week.block)
        target = db.session.get(TrainingWeek, request.form.get("target_week_id", type=int))
        if target is None:
            abort(400, description="Choose an available destination week.")
        require_programming_access(target)
        try:
            move(source, target)
        except ValueError as error:
            abort(409, description=str(error))
        return redirect(url_for("programming.week", week_id=target.id, _anchor=f"session-{source.id}"))

    @blueprint.post("/programming/sessions/<int:session_id>/delete")
    def delete_session(session_id: int):
        item = db.session.get(TrainingSession, session_id)
        require_programming_access(item)
        check_current(item.week.block)
        week_id = delete(item)
        return redirect(url_for("programming.week", week_id=week_id))
