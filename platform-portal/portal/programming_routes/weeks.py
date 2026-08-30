from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload, selectinload

from ..extensions import db
from ..models.exercise_library import Exercise
from ..models.programming import (
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from ..programming_services.prescriptions import PRESCRIPTION_MODE_LABELS
from ..programming_services.presentation import week_exposure_summary
from ..programming_services.weeks import (
    FinalWeekDeletionError,
    create,
    delete,
    duplicate,
    extend,
    reorder,
    update,
)
from ..services.weekly_programming_intelligence import map_athlete_programming_context
from ..tenancy import require_programming_access


def register_week_routes(blueprint: Blueprint) -> None:
    @blueprint.post("/programming/blocks/<int:block_id>/weeks")
    def create_week(block_id: int):
        block = db.session.get(TrainingBlock, block_id)
        require_programming_access(block)
        week = create(
            block,
            name=request.form.get("name", "").strip(),
            notes=request.form.get("notes", "").strip() or None,
        )
        return redirect(url_for("programming.week", week_id=week.id))

    @blueprint.get("/programming/weeks/<int:week_id>")
    def week(week_id: int):
        item = (
            TrainingWeek.query.options(
                joinedload(TrainingWeek.block).joinedload(TrainingBlock.athlete),
                selectinload(TrainingWeek.sessions).selectinload(
                    TrainingSession.prescriptions
                ),
                selectinload(TrainingWeek.sessions)
                .selectinload(TrainingSession.lift_slots)
                .selectinload(ProgrammingLiftSlot.prescriptions),
            )
            .filter_by(id=week_id)
            .one_or_none()
        )
        if item is None:
            abort(404)
        require_programming_access(item)
        return render_template(
            "programming/week.html",
            week=item,
            prescription_modes=PRESCRIPTION_MODE_LABELS,
            exposure_summary=week_exposure_summary(item),
            athlete_context=map_athlete_programming_context(item.block.athlete),
            lift_exercises=Exercise.query.filter(
                Exercise.active.is_(True), Exercise.lift_family.isnot(None)
            ).order_by(Exercise.lift_family, Exercise.name).all(),
        )

    @blueprint.post("/programming/weeks/<int:week_id>/duplicate")
    def duplicate_week(week_id: int):
        source = db.session.get(TrainingWeek, week_id)
        require_programming_access(source)
        target = duplicate(source)
        return redirect(url_for("programming.week", week_id=target.id))

    @blueprint.post("/programming/weeks/<int:week_id>/edit")
    def edit_week(week_id: int):
        item = db.session.get(TrainingWeek, week_id)
        require_programming_access(item)
        try:
            update(
                item,
                name=request.form.get("name", "").strip(),
                notes=request.form.get("notes", "").strip() or None,
            )
        except ValueError:
            abort(400)
        return redirect(url_for("programming.week", week_id=item.id))

    @blueprint.post("/programming/weeks/<int:week_id>/reorder")
    def reorder_week(week_id: int):
        item = db.session.get(TrainingWeek, week_id)
        require_programming_access(item)
        try:
            position = int(request.form.get("position", ""))
            reorder(item, position=position)
        except (TypeError, ValueError):
            abort(400)
        return redirect(url_for("programming.block", block_id=item.block_id))

    @blueprint.post("/programming/blocks/<int:block_id>/extend")
    def extend_block(block_id: int):
        block = db.session.get(TrainingBlock, block_id)
        require_programming_access(block)
        raw_count = (
            request.form.get("weeks")
            or request.form.get("week_count")
            or request.form.get("count", "1")
        )
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            abort(400)
        if count < 1:
            abort(400)
        try:
            extend(block, count=count)
        except ValueError:
            abort(409)
        return redirect(url_for("programming.block", block_id=block.id))

    @blueprint.post("/programming/weeks/<int:week_id>/delete")
    def delete_week(week_id: int):
        item = db.session.get(TrainingWeek, week_id)
        require_programming_access(item)
        try:
            block_id = delete(item)
        except FinalWeekDeletionError:
            abort(409)
        return redirect(url_for("programming.block", block_id=block_id))
