from flask import Blueprint, abort, redirect, render_template, request, url_for

from ..extensions import db
from ..models.athlete import Athlete
from ..models.programming import TrainingBlock
from ..programming_services.blocks import (
    BlockActivationError,
    activate,
    archive,
    create,
    delete_draft,
    duplicate,
)
from ..programming_services.presentation import week_exposure_summary


def register_block_routes(blueprint: Blueprint) -> None:
    @blueprint.post("/programming/blocks")
    def create_block():
        athlete_id = request.form.get("athlete_id", type=int)
        name = request.form.get("name", "").strip()
        athlete = db.session.get(Athlete, athlete_id) if athlete_id else None
        if athlete is None or not name:
            abort(400)
        block = create(
            athlete,
            name=name,
            objective=request.form.get("objective", "").strip() or None,
        )
        return redirect(url_for("programming.block", block_id=block.id))

    @blueprint.post("/programming/blocks/<int:block_id>/duplicate")
    def duplicate_block(block_id: int):
        source = db.session.get(TrainingBlock, block_id)
        if source is None:
            abort(404)
        target = duplicate(source)
        return redirect(url_for("programming.block", block_id=target.id))

    @blueprint.post("/programming/blocks/<int:block_id>/activate")
    def activate_block(block_id: int):
        item = db.session.get(TrainingBlock, block_id)
        if item is None:
            abort(404)
        try:
            activate(item)
        except BlockActivationError as error:
            abort(409, description=str(error))
        return redirect(url_for("programming.block", block_id=item.id))

    @blueprint.post("/programming/blocks/<int:block_id>/archive")
    def archive_block(block_id: int):
        item = db.session.get(TrainingBlock, block_id)
        if item is None:
            abort(404)
        archive(item)
        return redirect(
            url_for("programming.athlete_program", athlete_id=item.athlete_id)
        )

    @blueprint.post("/programming/blocks/<int:block_id>/delete")
    def delete_draft_block(block_id: int):
        item = db.session.get(TrainingBlock, block_id)
        if item is None:
            abort(404)
        if item.status != "draft":
            abort(409)
        athlete_id = delete_draft(item)
        return redirect(url_for("programming.athlete_program", athlete_id=athlete_id))

    @blueprint.get("/programming/blocks/<int:block_id>")
    def block(block_id: int):
        item = db.session.get(TrainingBlock, block_id)
        if item is None:
            abort(404)
        return render_template(
            "programming/block.html",
            block=item,
            week_exposures={
                week.id: week_exposure_summary(week) for week in item.weeks
            },
        )
