from flask import Blueprint, abort, redirect, render_template, request, url_for

from ..extensions import db
from ..models.programming import TrainingBlock, TrainingWeek
from ..programming_services.weeks import create, duplicate


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
