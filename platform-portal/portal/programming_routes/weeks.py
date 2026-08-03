from flask import Blueprint, abort, redirect, render_template, request, url_for

from ..extensions import db
from ..models.programming import TrainingBlock, TrainingWeek
from ..programming_services.weeks import (
    FinalWeekDeletionError,
    create,
    delete,
    duplicate,
    extend,
)


def register_week_routes(blueprint: Blueprint) -> None:
    @blueprint.post("/programming/blocks/<int:block_id>/weeks")
    def create_week(block_id: int):
        block = db.session.get(TrainingBlock, block_id)
        if block is None:
            abort(404)
        week = create(
            block,
            name=request.form.get("name", "").strip(),
            notes=request.form.get("notes", "").strip() or None,
        )
        return redirect(url_for("programming.week", week_id=week.id))

    @blueprint.get("/programming/weeks/<int:week_id>")
    def week(week_id: int):
        item = db.session.get(TrainingWeek, week_id)
        if item is None:
            abort(404)
        return render_template("programming/week.html", week=item)

    @blueprint.post("/programming/weeks/<int:week_id>/duplicate")
    def duplicate_week(week_id: int):
        source = db.session.get(TrainingWeek, week_id)
        if source is None:
            abort(404)
        target = duplicate(source)
        return redirect(url_for("programming.week", week_id=target.id))

    @blueprint.post("/programming/blocks/<int:block_id>/extend")
    def extend_block(block_id: int):
        block = db.session.get(TrainingBlock, block_id)
        if block is None:
            abort(404)
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
        if item is None:
            abort(404)
        try:
            block_id = delete(item)
        except FinalWeekDeletionError:
            abort(409)
        return redirect(url_for("programming.block", block_id=block_id))
