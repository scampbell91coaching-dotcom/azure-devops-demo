from __future__ import annotations

from datetime import UTC, datetime

from ..models.client_service import ClientServiceChange

SERVICE_DEFINITIONS = (
    ("training", "Training coaching", ("yes", "no")),
    ("nutrition", "Nutrition coaching", ("yes", "no")),
    ("meet_day", "Meet-day support", ("yes", "no")),
    ("video_review", "Video review", ("none", "limited", "included")),
)
DEFAULTS = {
    "training": "yes",
    "nutrition": "no",
    "meet_day": "no",
    "video_review": "none",
}


def resolved_client_services(athlete_id: int, *, now: datetime | None = None):
    """Return each effective service value and its next scheduled decision."""
    at = (now or datetime.now(UTC)).replace(tzinfo=None)
    changes = (
        ClientServiceChange.query.filter_by(athlete_id=athlete_id)
        .order_by(ClientServiceChange.effective_at.asc(), ClientServiceChange.id.asc())
        .all()
    )
    result = []
    for key, label, choices in SERVICE_DEFINITIONS:
        service_changes = [change for change in changes if change.service == key]
        effective = [change for change in service_changes if change.effective_at <= at]
        scheduled = next(
            (change for change in service_changes if change.effective_at > at), None
        )
        current = effective[-1] if effective else None
        result.append(
            {
                "key": key,
                "label": label,
                "choices": choices,
                "value": current.value if current else DEFAULTS[key],
                "provenance": (
                    current.changed_by.email
                    if current and current.changed_by
                    else "Service default"
                ),
                "effective_at": current.effective_at if current else None,
                "scheduled": scheduled,
            }
        )
    return result
