from __future__ import annotations

from typing import Any

from ..models.platform_snapshot import PlatformSnapshot
from ..repositories.platform_snapshot_repository import PlatformSnapshotRepository


class SnapshotIngestionService:
    def __init__(
        self,
        repository: PlatformSnapshotRepository | None = None,
    ) -> None:
        self.repository = repository or PlatformSnapshotRepository()

    def ingest(self, status: dict[str, Any]) -> PlatformSnapshot:
        checks = status.get("checks", [])
        security_pass_count = sum(
            1
            for check in checks
            if check.get("area") in {"Security", "Identity", "Networking"}
            and check.get("status") == "PASS"
        )

        snapshot = PlatformSnapshot(
            platform_score=int(status.get("score", 0)),
            http_status=str(status.get("availability", {}).get("http_code", "000")),
            health_latency_seconds=float(
                status.get("availability", {}).get("health_latency_seconds", 0.0)
            ),
            ready_nodes=int(status.get("platform", {}).get("nodes_ready", 0)),
            total_nodes=int(status.get("platform", {}).get("nodes_total", 0)),
            ready_replicas=int(status.get("workload", {}).get("ready_replicas", 0)),
            desired_replicas=int(status.get("workload", {}).get("desired_replicas", 0)),
            container_restarts=int(
                status.get("workload", {}).get("container_restarts", 0)
            ),
            argo_sync_status=str(
                status.get("gitops", {}).get("sync_status", "unknown")
            ),
            argo_health_status=str(
                status.get("gitops", {}).get("health_status", "unknown")
            ),
            security_pass_count=security_pass_count,
            warning_count=int(status.get("summary", {}).get("warn", 0)),
            failure_count=int(status.get("summary", {}).get("fail", 0)),
            git_revision=str(status.get("git", {}).get("revision", "unknown")),
            git_branch=str(status.get("git", {}).get("branch", "unknown")),
        )
        return self.repository.add(snapshot)
