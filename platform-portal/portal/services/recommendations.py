from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ..repositories.platform_snapshot_repository import PlatformSnapshotRepository


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
    def __init__(
        self,
        repository: PlatformSnapshotRepository | None = None,
    ) -> None:
        self.repository = repository or PlatformSnapshotRepository()

    def generate(self, hours: int = 24) -> dict[str, Any]:
        snapshots = self.repository.list_since(hours=hours)

        if not snapshots:
            recommendation = Recommendation(
                severity="warning",
                category="data",
                title="No historical data available",
                detail="The platform database has no snapshots in the selected range.",
                action="Confirm the snapshot timer is active and ingestion is succeeding.",
            )
            return {
                "status": "warning",
                "hours": hours,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "recommendations": [recommendation.to_dict()],
                "summary": {"critical": 0, "warning": 1, "info": 0},
            }

        latest = snapshots[-1]
        first = snapshots[0]
        recommendations: list[Recommendation] = []

        self._check_failures(latest, recommendations)
        self._check_score(latest, recommendations)
        self._check_gitops(latest, recommendations)
        self._check_latency(first, latest, recommendations)
        self._check_restarts(first, latest, recommendations)
        self._check_freshness(latest, recommendations)

        if not recommendations:
            recommendations.append(
                Recommendation(
                    severity="info",
                    category="platform",
                    title="Platform operating normally",
                    detail=(
                        "No material reliability, GitOps, latency, restart, "
                        "or data-freshness issues were detected."
                    ),
                    action="Continue monitoring normal platform trends.",
                )
            )

        summary = {
            "critical": sum(item.severity == "critical" for item in recommendations),
            "warning": sum(item.severity == "warning" for item in recommendations),
            "info": sum(item.severity == "info" for item in recommendations),
        }

        status = (
            "critical"
            if summary["critical"]
            else ("warning" if summary["warning"] else "healthy")
        )

        return {
            "status": status,
            "hours": hours,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latest_snapshot": latest.to_dict(),
            "recommendations": [item.to_dict() for item in recommendations],
            "summary": summary,
        }

    @staticmethod
    def _check_failures(latest, recommendations: list[Recommendation]) -> None:
        if latest.failure_count > 0:
            recommendations.append(
                Recommendation(
                    severity="critical",
                    category="reliability",
                    title="Platform checks are failing",
                    detail=(
                        f"The latest snapshot contains "
                        f"{latest.failure_count} failed checks."
                    ),
                    action="Open the platform status view and investigate failed checks.",
                )
            )

    @staticmethod
    def _check_score(latest, recommendations: list[Recommendation]) -> None:
        if latest.platform_score < 80:
            severity = "critical"
        elif latest.platform_score < 95:
            severity = "warning"
        else:
            return

        recommendations.append(
            Recommendation(
                severity=severity,
                category="platform",
                title="Platform score below target",
                detail=f"The latest platform score is {latest.platform_score}%.",
                action="Review failed and warning checks contributing to the score.",
            )
        )

    @staticmethod
    def _check_gitops(latest, recommendations: list[Recommendation]) -> None:
        if (
            latest.argo_sync_status != "Synced"
            or latest.argo_health_status != "Healthy"
        ):
            recommendations.append(
                Recommendation(
                    severity="critical",
                    category="gitops",
                    title="GitOps state requires attention",
                    detail=(
                        f"Argo CD reports sync={latest.argo_sync_status} "
                        f"and health={latest.argo_health_status}."
                    ),
                    action="Inspect the Argo CD application and reconcile drift.",
                )
            )

    @staticmethod
    def _check_latency(first, latest, recommendations: list[Recommendation]) -> None:
        if first.health_latency_seconds <= 0:
            return

        increase = (
            latest.health_latency_seconds - first.health_latency_seconds
        ) / first.health_latency_seconds

        if latest.health_latency_seconds >= 1.0 or increase >= 0.50:
            severity = "critical"
        elif latest.health_latency_seconds >= 0.50 or increase >= 0.25:
            severity = "warning"
        else:
            return

        recommendations.append(
            Recommendation(
                severity=severity,
                category="performance",
                title="Health latency has increased",
                detail=(
                    f"Latency changed from "
                    f"{first.health_latency_seconds:.3f}s to "
                    f"{latest.health_latency_seconds:.3f}s."
                ),
                action="Review ingress, application telemetry, and recent deployments.",
            )
        )

    @staticmethod
    def _check_restarts(first, latest, recommendations: list[Recommendation]) -> None:
        restart_increase = latest.container_restarts - first.container_restarts

        if restart_increase <= 0:
            return

        severity = "critical" if restart_increase >= 3 else "warning"
        recommendations.append(
            Recommendation(
                severity=severity,
                category="reliability",
                title="Container restart count increased",
                detail=(
                    f"Restart count increased by {restart_increase} "
                    "during the selected range."
                ),
                action="Inspect pod events, logs, probes, and resource limits.",
            )
        )

    @staticmethod
    def _check_freshness(latest, recommendations: list[Recommendation]) -> None:
        recorded_at = latest.recorded_at
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)

        age_minutes = (datetime.now(timezone.utc) - recorded_at).total_seconds() / 60

        if age_minutes <= 15:
            return

        recommendations.append(
            Recommendation(
                severity="warning",
                category="data",
                title="Platform history is stale",
                detail=f"The latest snapshot is {age_minutes:.0f} minutes old.",
                action="Check the platform snapshot systemd timer and service logs.",
            )
        )
