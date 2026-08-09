from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FRESHNESS_SECONDS = 15 * 60


class JsonStatusRepository:
    """Read the collector snapshot and attach conservative freshness metadata."""

    def __init__(self, path=None, freshness_seconds=None, now=None):
        default = Path(__file__).resolve().parents[2] / "data" / "platform-status.json"
        configured_path = path or os.getenv("PLATFORM_STATUS_FILE")
        self.configured = configured_path is not None
        self.path = Path(configured_path or default)
        threshold = freshness_seconds or os.getenv(
            "PLATFORM_STATUS_FRESHNESS_SECONDS", DEFAULT_FRESHNESS_SECONDS
        )
        try:
            self.freshness_seconds = max(1, int(threshold))
        except (TypeError, ValueError):
            self.freshness_seconds = DEFAULT_FRESHNESS_SECONDS
        self._now = now or (lambda: datetime.now(timezone.utc))

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            state = "unavailable" if self.configured else "not_configured"
            detail = (
                f"Configured status snapshot is missing: {self.path}"
                if self.configured
                else "PLATFORM_STATUS_FILE is not configured"
            )
            return self._failure(state, detail)
        try:
            with self.path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            return self._failure("unavailable", f"Unable to read status data: {exc}")

        if not isinstance(data, dict):
            return self._failure("unavailable", "Status snapshot must be a JSON object")

        generated_at = self._parse_timestamp(data.get("generated_at"))
        if generated_at is None:
            return self._failure(
                "unavailable", "Status snapshot has no valid generated_at timestamp"
            )

        age_seconds = (self._now() - generated_at).total_seconds()
        if age_seconds < -60:
            return self._failure(
                "unavailable", "Status snapshot generated_at is in the future"
            )
        age_seconds = max(0, age_seconds)
        result = dict(data)
        result["freshness"] = {
            "state": (
                "current" if age_seconds <= self.freshness_seconds else "stale"
            ),
            "generated_at": generated_at.isoformat(),
            "age_seconds": round(age_seconds),
            "threshold_seconds": self.freshness_seconds,
        }
        return result

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _failure(self, state: str, detail: str) -> dict[str, Any]:
        return {
            "generated_at": None,
            "score": None,
            "summary": {"pass": 0, "warn": 0, "fail": 1},
            "freshness": {
                "state": state,
                "generated_at": None,
                "age_seconds": None,
                "threshold_seconds": self.freshness_seconds,
            },
            "checks": [
                {
                    "area": "Portal",
                    "name": "Status data",
                    "status": "FAIL",
                    "detail": detail,
                }
            ],
        }
