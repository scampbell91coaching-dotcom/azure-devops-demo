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
        "block": _values(block, ("id", "athlete_id", "name", "objective", "status", "start_date", "timezone")),
        "weeks": weeks,
        "warmup_assignments": assignments,
        "warmup_overrides": overrides,
    }


def structured_diff(before: dict[str, Any] | None, after: dict[str, Any]) -> list[dict[str, Any]]:
    """Return coach-readable material changes, ignoring ids and internal ordering noise."""
    if not before:
        return [{"location": "Programme", "field": "programme", "old": None, "new": "Created"}]
    changes: list[dict[str, Any]] = []

    def compare(location: str, left: dict[str, Any], right: dict[str, Any], fields: tuple[str, ...]) -> None:
        for field in fields:
            if left.get(field) != right.get(field):
                changes.append({"location": location, "field": field.replace("_", " "), "old": left.get(field), "new": right.get(field)})

    compare("Programme", before.get("block", {}), after.get("block", {}), ("name", "objective", "status", "start_date", "timezone"))
    old_weeks = {row.get("id"): row for row in before.get("weeks", [])}
    new_weeks = {row.get("id"): row for row in after.get("weeks", [])}
    for week_id in old_weeks.keys() | new_weeks.keys():
        old_week, new_week = old_weeks.get(week_id), new_weeks.get(week_id)
        if old_week is None or new_week is None:
            row = new_week or old_week or {}
            changes.append({"location": f"Week {row.get('position', '?')}", "field": "week", "old": old_week and old_week.get("name"), "new": new_week and new_week.get("name")})
            continue
        week_location = f"Week {new_week.get('position', '?')} · {new_week.get('name', '')}"
        compare(week_location, old_week, new_week, ("name", "notes"))
        old_sessions = {row.get("id"): row for row in old_week.get("sessions", [])}
        new_sessions = {row.get("id"): row for row in new_week.get("sessions", [])}
        for session_id in old_sessions.keys() | new_sessions.keys():
            old_session, new_session = old_sessions.get(session_id), new_sessions.get(session_id)
            row = new_session or old_session or {}
            location = f"{week_location} / Session {row.get('position', '?')} · {row.get('name', '')}"
            if old_session is None or new_session is None:
                changes.append({"location": location, "field": "session", "old": old_session and old_session.get("name"), "new": new_session and new_session.get("name")})
                continue
            compare(location, old_session, new_session, ("name", "day_label", "notes"))
            old_rows = {row.get("id"): row for row in old_session.get("prescriptions", [])}
            new_rows = {row.get("id"): row for row in new_session.get("prescriptions", [])}
            for row_id in old_rows.keys() | new_rows.keys():
                left, right = old_rows.get(row_id), new_rows.get(row_id)
                item = right or left or {}
                item_location = f"{location} / {item.get('exercise_name', 'Prescription')}"
                if left is None or right is None:
                    changes.append({"location": item_location, "field": "prescription", "old": left and left.get("exercise_name"), "new": right and right.get("exercise_name")})
                    continue
                compare(item_location, left, right, tuple(field for field in PRESCRIPTION_FIELDS if field not in {"id", "position", "exercise_id", "lift_slot_id"}))
    return changes


def revision_diffs(revisions: list[ProgrammeRevision]) -> dict[int, list[dict[str, Any]]]:
    chronological = sorted(revisions, key=lambda row: row.revision_number)
    output: dict[int, list[dict[str, Any]]] = {}
    previous = None
    for revision in chronological:
        output[revision.id] = structured_diff(previous, revision.authored_snapshot)
        previous = revision.authored_snapshot
    return output


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
