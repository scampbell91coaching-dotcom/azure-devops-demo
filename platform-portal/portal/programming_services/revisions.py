from __future__ import annotations

from typing import Any

from flask import g, has_request_context, request

from ..extensions import db
from ..models.programming import ProgrammeRevision, TrainingBlock
from ..models.warmup import WarmupAssignment, WarmupOverride


PRESCRIPTION_FIELDS = (
    "id", "exercise_id", "lift_slot_id", "slot_role", "provenance",
    "exercise_name", "position", "prescription_type", "sets", "reps",
    "reps_min", "reps_max", "load_kg", "load_cap_kg", "percentage", "rpe",
    "rpe_min", "rpe_max", "rpe_cap", "target_reps", "target_rpe",
    "target_load_kg", "amrap", "tempo", "rest_seconds", "notes",
)


def _values(item: object, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: getattr(item, field) for field in fields}


def authored_snapshot(block: TrainingBlock) -> dict[str, Any]:
    """Capture authored values verbatim; derived presentation is intentionally absent."""
    weeks = []
    session_ids = []
    for week in sorted(block.weeks, key=lambda row: (row.position, row.id or 0)):
        sessions = []
        for session in sorted(week.sessions, key=lambda row: (row.position, row.id or 0)):
            if session.id is not None:
                session_ids.append(session.id)
            sessions.append({
                **_values(session, ("id", "name", "day_label", "position", "notes")),
                "lift_slots": [
                    _values(slot, ("id", "position", "lift_family"))
                    for slot in sorted(session.lift_slots, key=lambda row: (row.position, row.id or 0))
                ],
                "prescriptions": [
                    _values(row, PRESCRIPTION_FIELDS)
                    for row in sorted(session.prescriptions, key=lambda row: (row.position, row.id or 0))
                ],
            })
        weeks.append({
            **_values(week, ("id", "name", "position", "notes")),
            "sessions": sessions,
        })

    assignments = []
    overrides = []
    if session_ids:
        assignments = [
            _values(row, ("id", "session_id", "protocol_id", "athlete_id", "assigned_by_user_id", "reason"))
            for row in WarmupAssignment.query.filter(WarmupAssignment.session_id.in_(session_ids)).order_by(WarmupAssignment.id)
        ]
        overrides = [
            _values(row, ("id", "session_id", "athlete_id", "action", "target_key", "phase", "name", "kind", "sets", "reps", "duration_seconds", "percentage", "load_kg", "rest_seconds", "notes", "reason", "created_by_user_id"))
            for row in WarmupOverride.query.filter(WarmupOverride.session_id.in_(session_ids)).order_by(WarmupOverride.id)
        ]
    return {
        "schema_version": 1,
        "block": _values(block, ("id", "athlete_id", "name", "objective", "status")),
        "weeks": weeks,
        "warmup_assignments": assignments,
        "warmup_overrides": overrides,
    }


def append_revision(
    block: TrainingBlock,
    *,
    change_type: str,
    summary: str,
    reason: str | None = None,
) -> ProgrammeRevision:
    """Append a revision in the caller's transaction after its edits are flushed."""
    db.session.flush()
    actor = g.get("current_user") if has_request_context() else None
    supplied_reason = request.form.get("revision_reason", "").strip() if has_request_context() else ""
    latest = (
        db.session.query(db.func.max(ProgrammeRevision.revision_number))
        .filter_by(block_id=block.id)
        .scalar()
        or 0
    )
    revision = ProgrammeRevision(
        block=block,
        athlete_id=block.athlete_id,
        revision_number=latest + 1,
        change_type=change_type,
        summary=summary,
        reason=supplied_reason or reason or summary,
        authored_snapshot=authored_snapshot(block),
        authored_by_user_id=getattr(actor, "id", None),
        authored_by=getattr(actor, "email", None) or "System",
    )
    db.session.add(revision)
    return revision
