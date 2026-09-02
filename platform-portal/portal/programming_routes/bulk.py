from flask import Blueprint, abort, redirect, render_template, request, url_for

from ..extensions import db
from ..models.programming import TrainingBlock
from ..programming_services.bulk import apply, preview
from ..programming_services.conflicts import ProgrammeConflictError, require_current, require_editable
from ..tenancy import require_programming_access


def register_bulk_routes(blueprint: Blueprint) -> None:
    @blueprint.post("/programming/blocks/<int:block_id>/bulk-preview")
    def bulk_preview(block_id: int):
        block = db.session.get(TrainingBlock, block_id)
        require_programming_access(block)
        try:
            require_editable(block)
            require_current(block, request.form.get("expected_revision", type=int))
            field = request.form.get("field", "")
            value = request.form.get("value", "")
            week_ids = set(request.form.getlist("week_id", type=int))
            changes = preview(block, week_ids, field, value)
        except (ValueError, ProgrammeConflictError) as error:
            abort(409, description=str(error))
        return render_template("programming/bulk_preview.html", block=block, changes=changes,
            field=field, value=value, week_ids=sorted(week_ids),
            expected_revision=request.form.get("expected_revision", type=int))

    @blueprint.post("/programming/blocks/<int:block_id>/bulk-apply")
    def bulk_apply(block_id: int):
        block = db.session.get(TrainingBlock, block_id)
        require_programming_access(block)
        try:
            require_editable(block)
            require_current(block, request.form.get("expected_revision", type=int))
            changes = preview(block, set(request.form.getlist("week_id", type=int)),
                              request.form.get("field", ""), request.form.get("value", ""))
            apply(block, changes, reason=request.form.get("revision_reason", ""))
        except (ValueError, ProgrammeConflictError) as error:
            abort(409, description=str(error))
        return redirect(url_for("programming.block", block_id=block.id))
