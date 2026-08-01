from __future__ import annotations

from typing import Any

from ..repositories.platform_snapshot_repository import PlatformSnapshotRepository


class HistoryService:
    def __init__(
        self,
        repository: PlatformSnapshotRepository | None = None,
    ) -> None:
        self.repository = repository or PlatformSnapshotRepository()

    def recent(self, limit: int = 288) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.repository.list_recent(limit=limit)]

    def chart(self, hours: int = 24) -> dict[str, list[Any]]:
        snapshots = self.repository.list_since(hours=hours)
        return {
            "labels": [item.recorded_at.isoformat() for item in snapshots],
            "score": [item.platform_score for item in snapshots],
            "latency": [item.health_latency_seconds for item in snapshots],
            "restarts": [item.container_restarts for item in snapshots],
        }
