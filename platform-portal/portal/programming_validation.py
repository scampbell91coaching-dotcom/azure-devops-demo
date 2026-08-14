"""Bounded request validation for coach programming JSON endpoints."""

from __future__ import annotations

import math
from typing import Any

from flask import abort, request
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge


PROGRAMMING_JSON_MAX_BYTES = 64 * 1024


def require_json_object(*, allowed_keys: frozenset[str]) -> dict[str, Any]:
    """Parse a small JSON object and reject ambiguous or unexpected input."""
    if request.content_length is not None and request.content_length > PROGRAMMING_JSON_MAX_BYTES:
        raise RequestEntityTooLarge()
    request.max_content_length = PROGRAMMING_JSON_MAX_BYTES
    if not request.is_json:
        abort(400, description="Content-Type must be application/json.")
    try:
        payload = request.get_json(silent=False)
    except (BadRequest, RequestEntityTooLarge):
        raise
    if not isinstance(payload, dict):
        abort(400, description="The JSON body must be an object.")
    unexpected = set(payload) - allowed_keys
    if unexpected:
        abort(400, description="Unexpected programming fields were supplied.")
    return payload


def optional_string(
    value: Any, *, field: str, maximum: int, allow_empty: bool = True
) -> str | None:
    if value is None:
        if not allow_empty:
            abort(400, description=f"{field} is required.")
        return None
    if not isinstance(value, str):
        abort(400, description=f"{field} must be a string.")
    result = value.strip()
    if not result and not allow_empty:
        abort(400, description=f"{field} is required.")
    if len(result) > maximum:
        abort(400, description=f"{field} is too long.")
    return result or None


def optional_int(
    value: Any, *, field: str, minimum: int, maximum: int
) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if (
            len(stripped) > 10
            or not stripped.isascii()
            or not stripped.isdecimal()
        ):
            abort(400, description=f"{field} must be an integer.")
        value = int(stripped)
    if not isinstance(value, int) or isinstance(value, bool):
        abort(400, description=f"{field} must be an integer.")
    if not minimum <= value <= maximum:
        abort(400, description=f"{field} is outside the allowed range.")
    return value


def optional_float(
    value: Any, *, field: str, minimum: float, maximum: float
) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            abort(400, description=f"{field} must be numeric.")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        abort(400, description=f"{field} must be numeric.")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        abort(400, description=f"{field} is outside the allowed range.")
    return result
