from typing import cast

from ..extensions import db
from ..models.programming import TrainingSession
from ..models.warmup import WarmupAssignment, WarmupOverride


def copy(source: TrainingSession, target: TrainingSession) -> None:
    """Copy authored warm-up intent, but never an athlete's resolved snapshot."""
    assignments = WarmupAssignment.query.filter_by(session_id=source.id).order_by(
        WarmupAssignment.id
    )
    for item in cast(list[WarmupAssignment], assignments.all()):
        db.session.add(
            WarmupAssignment(
                protocol_id=item.protocol_id,
                athlete_id=item.athlete_id,
                session_id=target.id,
                assigned_by_user_id=item.assigned_by_user_id,
                reason=item.reason,
            )
        )

    overrides = WarmupOverride.query.filter_by(session_id=source.id).order_by(
        WarmupOverride.id
    )
    fields = (
        "athlete_id",
        "action",
        "target_key",
        "phase",
        "name",
        "kind",
        "sets",
        "reps",
        "duration_seconds",
        "percentage",
        "load_kg",
        "rest_seconds",
        "notes",
        "reason",
        "created_by_user_id",
    )
    for item in cast(list[WarmupOverride], overrides.all()):
        values = {field: getattr(item, field) for field in fields}
        db.session.add(WarmupOverride(session_id=target.id, **values))
