"""Read-only adapters for the engineering overview.

This module deliberately consumes existing status and release evidence instead of
rerunning operational checks from a web request.
"""

from __future__ import annotations

import shutil
from typing import Any

from .platform_status import PlatformStatusService
from .release_readiness import ReleaseEvidenceService


class EngineeringOverviewService:
    TOOLCHAIN = ("git", "python3", "ruff", "pytest", "helm", "terraform", "kubectl")

    def __init__(
        self,
        status_service: PlatformStatusService | None = None,
        release_evidence_service: ReleaseEvidenceService | None = None,
    ) -> None:
        self.status_service = status_service or PlatformStatusService()
        self.release_evidence_service = release_evidence_service

    @staticmethod
    def _state(value: Any, positive: Any = True) -> str:
        if value is None:
            return "unavailable"
        return "available" if value == positive else "attention"

    def _platform(self) -> tuple[dict[str, Any], bool]:
        data = self.status_service.get_status()
        if not isinstance(data, dict):
            return {}, False
        # Repository error payloads do not have a collection timestamp and must
        # not be presented as live platform observations.
        return data, bool(data.get("generated_at"))

    def _release(self) -> dict[str, Any]:
        if self.release_evidence_service is None:
            return {
                "state": "unavailable",
                "label": "Not ready",
                "readiness": "not_ready",
                "detail": "Release evidence service is unavailable.",
                "generated_at": None,
                "checks": [],
                "href": "/release-readiness",
            }
        result = self.release_evidence_service.load()
        if not result.available:
            return {
                "state": "unavailable",
                "label": "Not ready",
                "readiness": result.readiness,
                "detail": result.error,
                "generated_at": None,
                "checks": [],
                "href": "/release-readiness",
            }
        evidence = result.evidence
        status = result.readiness
        state = "available" if status == "ready" else "attention"
        label = "Ready" if status == "ready" else "Not ready"
        return {
            "state": state,
            "label": label,
            "readiness": status,
            "detail": result.error
            or "From the existing local release-evidence report; no checks were rerun.",
            "generated_at": evidence.get("generated_at"),
            "freshness": result.freshness,
            "checks": evidence["checks"],
            "href": "/release-readiness",
        }

    def build(self) -> dict[str, Any]:
        platform, is_live = self._platform()
        availability = platform.get("availability", {}) if is_live else {}
        security = platform.get("security", {}) if is_live else {}
        gitops = platform.get("gitops", {}) if is_live else {}

        http_code = availability.get("http_code")
        health_state = self._state(http_code, "200")
        security_values = [
            security.get("run_as_non_root"),
            security.get("privilege_escalation_disabled"),
            security.get("seccomp_runtime_default"),
        ]
        if not is_live or all(value is None for value in security_values):
            security_state = "unavailable"
        else:
            security_state = "available" if all(security_values) else "attention"

        sync = gitops.get("sync_status")
        argo_health = gitops.get("health_status")
        gitops_state = (
            "unavailable"
            if not is_live or (sync is None and argo_health is None)
            else (
                "available"
                if sync == "Synced" and argo_health == "Healthy"
                else "attention"
            )
        )

        return {
            "generated_at": platform.get("generated_at") if is_live else None,
            "health": {
                "state": health_state,
                "label": (
                    "Healthy"
                    if health_state == "available"
                    else "Needs attention"
                    if health_state == "attention"
                    else "Unavailable"
                ),
                "detail": (
                    f"HTTP {http_code}"
                    if http_code is not None
                    else "Live platform status is unavailable."
                ),
                "href": "/observability",
            },
            "security": {
                "state": security_state,
                "label": (
                    "Controls present"
                    if security_state == "available"
                    else "Review required"
                    if security_state == "attention"
                    else "Unavailable"
                ),
                "detail": (
                    "From the existing platform security status."
                    if is_live
                    else "Live platform status is unavailable."
                ),
                "href": "/security",
            },
            "gitops": {
                "state": gitops_state,
                "label": (
                    f"{sync or 'Unknown'} / {argo_health or 'Unknown'}"
                    if sync or argo_health
                    else "Unavailable"
                ),
                "detail": (
                    "Live GitOps deployment state."
                    if gitops_state != "unavailable"
                    else "Live GitOps status is unavailable."
                ),
                "href": "/gitops",
            },
            "release": self._release(),
            "toolchain": [self._tool_status(tool) for tool in self.TOOLCHAIN],
        }

    @staticmethod
    def _tool_status(tool: str) -> dict[str, str]:
        available = shutil.which(tool) is not None
        return {
            "name": tool,
            "state": "available" if available else "unavailable",
            "label": "Available" if available else "Unavailable",
            "detail": "Portal host only; no version or remote status check was run.",
        }
