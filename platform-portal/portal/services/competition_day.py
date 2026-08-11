from __future__ import annotations

import json
from typing import Any


MARKER = "[[competition-day:v1]]"


def unpack_notes(value: str | None) -> tuple[str | None, dict[str, Any]]:
    """Read prototype workflow metadata while preserving legacy free-text notes."""
    if not value or not value.startswith(MARKER):
        return value, {}
    payload = value[len(MARKER) :]
    try:
        decoded = json.loads(payload)
    except (TypeError, ValueError):
        return value, {}
    if not isinstance(decoded, dict):
        return value, {}
    notes = decoded.pop("notes", None)
    return notes if isinstance(notes, str) and notes else None, decoded


def pack_notes(notes: str | None, metadata: dict[str, Any]) -> str | None:
    """Store workflow metadata in an existing notes column (no schema revision)."""
    cleaned = {key: value for key, value in metadata.items() if value not in (None, "")}
    if not cleaned:
        return notes or None
    return MARKER + json.dumps(
        {"notes": notes or None, **cleaned}, sort_keys=True, separators=(",", ":")
    )
