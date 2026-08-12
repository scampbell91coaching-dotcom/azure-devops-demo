"""Read-only diagnostics for metadata used by automatic accessory selection."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from ..models.exercise_library import Exercise


JSON_LIST_FIELDS = (
    "equipment_options",
    "constraint_tags",
    "lift_relevance",
    "training_phases",
    "compatibility_tags",
)


def _json_list_state(value: str | None) -> str:
    if value is None or not value.strip():
        return "missing"
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return "invalid"
    if not isinstance(parsed, list) or any(
        not isinstance(item, str) or not item.strip() for item in parsed
    ):
        return "invalid"
    return "populated" if parsed else "empty"


def build_exercise_catalogue_diagnostic(
    exercises: Iterable[Exercise],
) -> dict[str, Any]:
    """Summarise selection readiness without modifying catalogue rows."""
    active = [row for row in exercises if row.active]
    suitable = [row for row in active if row.accessory_suitable]
    automatic = [row for row in active if row.auto_select]
    eligible = [row for row in suitable if row.auto_select]

    fatigue_issues = [
        {"id": row.id, "name": row.name, "value": row.fatigue_rating}
        for row in suitable
        if isinstance(row.fatigue_rating, bool)
        or not isinstance(row.fatigue_rating, int)
        or not 1 <= row.fatigue_rating <= 5
    ]

    coverage: dict[str, dict[str, int]] = {}
    for field in JSON_LIST_FIELDS:
        states = {"populated": 0, "empty": 0, "missing": 0, "invalid": 0}
        for row in suitable:
            states[_json_list_state(getattr(row, field))] += 1
        coverage[field] = states

    inconsistencies: list[dict[str, Any]] = []
    for row in active:
        reasons: list[str] = []
        if row.auto_select and not row.accessory_suitable:
            reasons.append("auto_select is blocked because accessory_suitable is false")
        if row.accessory_suitable and row.movement == "warmup":
            reasons.append("warmup movement is marked accessory_suitable")
        if row.accessory_suitable and row.category == "competition":
            reasons.append("competition category is marked accessory_suitable")
        if row.lift_family not in (None, "none", "squat", "bench", "deadlift"):
            reasons.append("lift_family is outside the supported taxonomy")
        if row.lift_family in ("squat", "bench", "deadlift") and row.movement not in (
            row.lift_family,
            "accessory",
        ):
            reasons.append("lift_family conflicts with movement")
        if row.auto_select:
            for field in ("lift_relevance", "training_phases", "compatibility_tags", "constraint_tags"):
                if _json_list_state(getattr(row, field)) == "invalid":
                    reasons.append(f"{field} is invalid JSON-list metadata")
        if reasons:
            inconsistencies.append({"id": row.id, "name": row.name, "reasons": reasons})

    return {
        "counts": {
            "active": len(active),
            "accessory_suitable": len(suitable),
            "auto_select": len(automatic),
            "automatic_selection_eligible": len(eligible),
            "accessory_suitable_not_auto_select": len(suitable) - len(eligible),
        },
        "fatigue_cost_issues": fatigue_issues,
        "accessory_metadata_coverage": coverage,
        "category_movement_inconsistencies": inconsistencies,
        "scope": "active rows; metadata coverage and fatigue checks use active accessory_suitable rows",
    }
