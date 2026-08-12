from __future__ import annotations

from typing import Any

from ..repositories.status_repository import JsonStatusRepository
from ..repositories.platform_snapshot_repository import PlatformSnapshotRepository
from .recommendations import RecommendationService


class ExecutiveDashboardService:
    """Build Overview from the same collector snapshot used by observability."""

    def __init__(
        self,
        repository=None,
        recommendation_service=None,
        snapshot_repository=None,
    ) -> None:
        self.repository = repository or JsonStatusRepository()
        self.recommendation_service = recommendation_service or RecommendationService(
            self.repository
        )
        self.snapshot_repository = snapshot_repository

    def build(self, hours: int = 24) -> dict[str, Any]:
        data = self.repository.load()
        freshness = data.get("freshness", {}) if isinstance(data, dict) else {}
        recommendations = self.recommendation_service.generate(hours=hours)
        if freshness.get("state") not in {"current", "stale"}:
            return {
                "status": freshness.get("state", "unavailable"),
                "freshness": freshness,
                "hours": hours,
                "latest": None,
                "trend": {"score_change": None, "latency_change": None, "restart_change": None},
                "summary": recommendations["summary"],
                "recommendations": recommendations["recommendations"][:3],
            }

        platform = _mapping(data.get("platform"))
        workload = _mapping(data.get("workload"))
        gitops = _mapping(data.get("gitops"))
        availability = _mapping(data.get("availability"))
        git = _mapping(data.get("git"))
        checks = data.get("checks", [])
        security_passes = sum(
            isinstance(item, dict)
            and item.get("area") in {"Security", "Identity", "Networking"}
            and item.get("status") == "PASS"
            for item in checks if isinstance(checks, list)
        )
        summary = _mapping(data.get("summary"))
        latest = {
            "recorded_at": data.get("generated_at"),
            "platform_score": data.get("score"),
            "ready_nodes": platform.get("nodes_ready"),
            "total_nodes": platform.get("nodes_total"),
            "node_readiness": f"{_display(platform.get('nodes_ready'))}/{_display(platform.get('nodes_total'))}",
            "ready_replicas": workload.get("ready_replicas"),
            "desired_replicas": workload.get("desired_replicas"),
            "replica_readiness": f"{_display(workload.get('ready_replicas'))}/{_display(workload.get('desired_replicas'))}",
            "container_restarts": workload.get("container_restarts"),
            "argo_sync_status": gitops.get("sync_status") or "unknown",
            "argo_health_status": gitops.get("health_status") or "unknown",
            "http_status": availability.get("http_code") or "unavailable",
            "health_latency_seconds": availability.get("health_latency_seconds"),
            "security_pass_count": security_passes,
            "warning_count": summary.get("warn", 0),
            "failure_count": summary.get("fail", 0),
            "git_revision": git.get("revision") or "not reported",
            "git_branch": git.get("branch") or "not reported",
        }
        trend = {
            "score_change": None,
            "latency_change": None,
            "restart_change": None,
        }

        snapshot_repository = self.snapshot_repository
        if snapshot_repository is None:
            try:
                snapshot_repository = PlatformSnapshotRepository()
                snapshots = snapshot_repository.list_since(hours=hours)
            except RuntimeError:
                snapshots = []
        else:
            snapshots = snapshot_repository.list_since(hours=hours)

        if len(snapshots) >= 2:
            first = snapshots[0]
            last = snapshots[-1]
            trend = {
                "score_change": last.platform_score - first.platform_score,
                "latency_change": round(
                    last.health_latency_seconds - first.health_latency_seconds,
                    4,
                ),
                "restart_change": last.container_restarts - first.container_restarts,
            }

        return {
            "status": "stale" if freshness.get("state") == "stale" else recommendations["status"],
            "freshness": freshness,
            "hours": hours,
            "latest": latest,
            "trend": trend,
            "summary": recommendations["summary"],
            "recommendations": recommendations["recommendations"][:3],
        }


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _display(value: Any) -> str:
    return str(value) if value is not None else "unknown"
