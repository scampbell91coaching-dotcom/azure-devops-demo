from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db


class PlatformSnapshot(db.Model):  # type: ignore[name-defined]
    __tablename__ = "platform_snapshots"

    id = db.Column(db.Integer, primary_key=True)

    recorded_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    platform_score = db.Column(db.Integer, nullable=False)

    http_status = db.Column(db.String(3), nullable=False)
    health_latency_seconds = db.Column(db.Float, nullable=False)

    ready_nodes = db.Column(db.Integer, nullable=False)
    total_nodes = db.Column(db.Integer, nullable=False)

    ready_replicas = db.Column(db.Integer, nullable=False)
    desired_replicas = db.Column(db.Integer, nullable=False)

    container_restarts = db.Column(db.Integer, nullable=False, default=0)

    argo_sync_status = db.Column(db.String(32), nullable=False)
    argo_health_status = db.Column(db.String(32), nullable=False)

    security_pass_count = db.Column(db.Integer, nullable=False, default=0)
    warning_count = db.Column(db.Integer, nullable=False, default=0)
    failure_count = db.Column(db.Integer, nullable=False, default=0)

    git_revision = db.Column(db.String(64), nullable=False)
    git_branch = db.Column(db.String(128), nullable=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "recorded_at": self.recorded_at.isoformat(),
            "platform_score": self.platform_score,
            "http_status": self.http_status,
            "health_latency_seconds": self.health_latency_seconds,
            "ready_nodes": self.ready_nodes,
            "total_nodes": self.total_nodes,
            "ready_replicas": self.ready_replicas,
            "desired_replicas": self.desired_replicas,
            "container_restarts": self.container_restarts,
            "argo_sync_status": self.argo_sync_status,
            "argo_health_status": self.argo_health_status,
            "security_pass_count": self.security_pass_count,
            "warning_count": self.warning_count,
            "failure_count": self.failure_count,
            "git_revision": self.git_revision,
            "git_branch": self.git_branch,
        }
