from __future__ import annotations

from typing import Any

from ..repositories.platform_snapshot_repository import PlatformSnapshotRepository
from .recommendations import RecommendationService


class ExecutiveDashboardService:
    def __init__(
        self,
        repository: PlatformSnapshotRepository | None = None,
        recommendation_service: RecommendationService | None = None,
    ) -> None:
        self.repository = repository or PlatformSnapshotRepository()
        self.recommendation_service = recommendation_service or RecommendationService(
            self.repository
        )

    def build(self, hours: int = 24) -> dict[str, Any]:
        recent = self.repository.list_since(hours=hours)
        latest = self.repository.latest()
        recommendations = self.recommendation_service.generate(hours=hours)

        if latest is None:
            return {
                "status": "warning",
                "hours": hours,
                "latest": None,
                "trend": {
                    "score_change": 0.0,
                    "latency_change": 0.0,
                    "restart_change": 0,
                },
                "summary": recommendations.get("summary", {}),
                "recommendations": recommendations.get("recommendations", []),
            }

        first = recent[0] if recent else latest

        score_change = latest.platform_score - first.platform_score
        latency_change = latest.health_latency_seconds - first.health_latency_seconds
        restart_change = latest.container_restarts - first.container_restarts

        latest_data = latest.to_dict()
        latest_data["node_readiness"] = f"{latest.ready_nodes}/{latest.total_nodes}"
        latest_data["replica_readiness"] = (
            f"{latest.ready_replicas}/{latest.desired_replicas}"
        )

        return {
            "status": recommendations.get("status", "unknown"),
            "hours": hours,
            "latest": latest_data,
            "trend": {
                "score_change": score_change,
                "latency_change": latency_change,
                "restart_change": restart_change,
            },
            "summary": recommendations.get("summary", {}),
            "recommendations": recommendations.get("recommendations", [])[:3],
        }
