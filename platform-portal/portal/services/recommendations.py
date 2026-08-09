from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ..repositories.status_repository import JsonStatusRepository


@dataclass(frozen=True)
class Recommendation:
    severity: str
    category: str
    title: str
    detail: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class RecommendationService:
    """Derive actions only from evidence in the current collector snapshot."""

    def __init__(self, repository=None) -> None:
        self.repository = repository or JsonStatusRepository()

    def generate(self, hours: int = 24) -> dict[str, Any]:
        data = self.repository.load()
        freshness = data.get("freshness", {}) if isinstance(data, dict) else {}
        recommendations: list[Recommendation] = []

        checks = data.get("checks", []) if isinstance(data, dict) else []
        for check in checks if isinstance(checks, list) else []:
            if not isinstance(check, dict):
                continue
            status = str(check.get("status", "")).upper()
            if status not in {"WARN", "FAIL"}:
                continue
            name = str(check.get("name") or "Platform check")
            area = str(check.get("area") or "platform")
            recommendations.append(
                Recommendation(
                    severity="critical" if status == "FAIL" else "warning",
                    category=area.lower(),
                    title=f"{name} requires attention",
                    detail=str(check.get("detail") or "No detail was reported."),
                    action=f"Investigate the {area} check in the platform status view.",
                )
            )

        state = freshness.get("state")
        if state == "stale":
            recommendations.append(
                Recommendation(
                    severity="warning",
                    category="data",
                    title="Platform status snapshot is stale",
                    detail=f"The last collection is {freshness.get('age_seconds')} seconds old.",
                    action="Inspect the platform-status-collector CronJob and its latest Job.",
                )
            )

        summary = {
            "critical": sum(item.severity == "critical" for item in recommendations),
            "warning": sum(item.severity == "warning" for item in recommendations),
            "info": 0,
        }
        status = (
            "critical" if summary["critical"] else
            "warning" if summary["warning"] else
            "healthy" if state == "current" else
            state or "unavailable"
        )
        return {
            "status": status,
            "hours": hours,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "snapshot_generated_at": data.get("generated_at") if isinstance(data, dict) else None,
            "freshness": freshness,
            "recommendations": [item.to_dict() for item in recommendations],
            "summary": summary,
        }
