"""Application-owned, coach-facing Block Factory golden programme definitions."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


GOLDEN_PROGRAMMES_PATH = Path(__file__).parents[2] / "data" / "golden_programmes.json"


@lru_cache(maxsize=1)
def golden_programmes() -> tuple[dict[str, Any], ...]:
    data = json.loads(GOLDEN_PROGRAMMES_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("programmes"), list):
        raise ValueError("Unsupported golden programme data")
    return tuple(data["programmes"])
