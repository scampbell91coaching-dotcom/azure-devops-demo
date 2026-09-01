from datetime import date
from flask import Blueprint, abort, redirect, render_template, request, url_for
from sqlalchemy.orm import joinedload, selectinload

from ..extensions import db
from ..models.athlete import Athlete
from ..models.programming import TrainingBlock, TrainingSession, TrainingWeek
from ..programming_services.blocks import (
    BlockActivationError,
    activate,
    close,
    create,
    delete_draft,
    duplicate,
    update,
)
from ..programming_services.conflicts import (
    ActiveProgrammeEditError, ProgrammeConflictError, current_revision,
    require_current, require_editable,
)
from ..programming_services.presentation import week_exposure_summary
from ..tenancy import athlete_query_for_request, require_athlete_access, require_programming_access


def register_block_routes(blueprint: Blueprint) -> None:
    def timing():
        raw = request.form.get("start_date", "").strip()
        try:
            start = date.fromisoformat(raw) if raw else None
        except ValueError:
            abort(400, description="Enter a valid programme start date.")
        return start, request.form.get("timezone", "UTC").strip() or "UTC"

    def expected_revision() -> int | None:
        raw = request.form.get("expected_revision")
        try:
            return int(raw) if raw not in (None, "") else None
        except ValueError:
            abort(400, description="Invalid programme revision token.")

    @blueprint.post("/programming/blocks")
    def create_block():
        athlete_id = request.form.get("athlete_id", type=int)
        name = request.form.get("name", "").strip()
        athlete = require_athlete_access(athlete_id) if athlete_id else None
        if athlete is None or not name:
            abort(400)
        start, timezone = timing()
        block = create(
            athlete,
            name=name,
            objective=request.form.get("objective", "").strip() or None,
            start_date=start, timezone=timezone,
        )
        return redirect(url_for("programming.block", block_id=block.id))

    @blueprint.post("/programming/blocks/<int:block_id>/duplicate")
    def duplicate_block(block_id: int):
        source = db.session.get(TrainingBlock, block_id)
        require_programming_access(source)
        target = duplicate(source)
        return redirect(url_for("programming.block", block_id=target.id))

    @blueprint.post("/programming/blocks/<int:block_id>/revise")
    def revise_block(block_id: int):
        source = db.session.get(TrainingBlock, block_id)
        require_programming_access(source)
        if source.status != "active":
            abort(409, description="Only an active programme can start a review draft.")
        try:
            require_current(source, expected_revision())
            target = duplicate(source, as_revision=True)
        except ProgrammeConflictError as error:
            abort(409, description=str(error))
        return redirect(url_for("programming.block", block_id=target.id))

    @blueprint.post("/programming/blocks/<int:block_id>/edit")
    def edit_block(block_id: int):
        item = db.session.get(TrainingBlock, block_id)
        require_programming_access(item)
        try:
            require_editable(item)
            require_current(item, expected_revision())
            start, timezone = timing()
            update(
                item,
                name=request.form.get("name", "").strip(),
                objective=request.form.get("objective", "").strip() or None,
                start_date=start, timezone=timezone,
            )
        except (ActiveProgrammeEditError, ProgrammeConflictError) as error:
            abort(409, description=str(error))
        except ValueError:
            abort(400)
        return redirect(url_for("programming.block", block_id=item.id))

    @blueprint.post("/programming/blocks/<int:block_id>/activate")
    def activate_block(block_id: int):
        item = db.session.get(TrainingBlock, block_id)
        require_programming_access(item)
        try:
            activate(
                item,
                expected_revision=expected_revision(),
                reason=request.form.get("revision_reason", "").strip() or None,
            )
        except (BlockActivationError, ProgrammeConflictError) as error:
            abort(409, description=str(error))
        return redirect(url_for("programming.block", block_id=item.id))

    @blueprint.post("/programming/blocks/<int:block_id>/close")
    @blueprint.post("/programming/blocks/<int:block_id>/archive")
    def archive_block(block_id: int):
        item = db.session.get(TrainingBlock, block_id)
        require_programming_access(item)
        try:
            close(item, outcome=request.form.get("outcome", ""))
        except BlockActivationError as error:
            abort(409, description=str(error))
        return redirect(
            url_for("programming.athlete_program", athlete_id=item.athlete_id)
        )

    @blueprint.post("/programming/blocks/<int:block_id>/delete")
    def delete_draft_block(block_id: int):
        item = db.session.get(TrainingBlock, block_id)
        require_programming_access(item)
        if item.status != "draft":
            abort(409)
        athlete_id = delete_draft(item)
        return redirect(url_for("programming.athlete_program", athlete_id=athlete_id))

    @blueprint.get("/programming/blocks/<int:block_id>")
    def block(block_id: int):
        item = (
            TrainingBlock.query.options(
                joinedload(TrainingBlock.athlete),
                selectinload(TrainingBlock.weeks)
                .selectinload(TrainingWeek.sessions)
                .selectinload(TrainingSession.lift_slots),
            )
            .filter_by(id=block_id)
            .one_or_none()
        )
        if item is None:
            abort(404)
        require_programming_access(item)
        return render_template(
            "programming/block.html",
            block=item,
            week_exposures={
                week.id: week_exposure_summary(week) for week in item.weeks
            },
            current_revision=current_revision(item),
            workspace_athletes=athlete_query_for_request().order_by(Athlete.last_name.asc()).all(),
        )
