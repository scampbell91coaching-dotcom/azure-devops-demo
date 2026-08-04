"""Read and validate the release evidence produced by the repository release gate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

EVIDENCE_RELATIVE_PATH = Path("evidence/release/release-evidence.json")
VALID_CHECK_STATUSES = frozenset({"pass", "fail", "skipped"})


class ReleaseEvidenceError(ValueError):
    """The release evidence exists but does not match its published contract."""


@dataclass(frozen=True)
class ReleaseEvidenceResult:
    evidence: dict[str, Any] | None
    error: str | None

    @property
    def available(self) -> bool:
        return self.evidence is not None

    @property
    def readiness(self) -> str:
        """Return the sole fail-closed readiness decision exposed to consumers."""
        return self.evidence["status"] if self.evidence is not None else "not_ready"


def release_evidence_path(repository_root: Path) -> Path:
    """Return the fixed evidence path below the repository root."""
    root = repository_root.resolve()
    path = (root / EVIDENCE_RELATIVE_PATH).resolve()
    if not path.is_relative_to(root):
        raise ReleaseEvidenceError("release evidence path escapes the repository root")
    return path


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseEvidenceError(f"{field} must be a non-empty string")
    return value


def _generated_datetime(value: str) -> datetime:
    try:
        generated_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseEvidenceError(
            "generated_at must be an ISO-8601 timestamp"
        ) from exc
    if generated_at.tzinfo is None:
        raise ReleaseEvidenceError("generated_at must include a timezone")
    return generated_at.astimezone(timezone.utc)


def parse_release_evidence(payload: Any) -> dict[str, Any]:
    """Validate and return release evidence without reimplementing its gate logic."""
    if not isinstance(payload, dict):
        raise ReleaseEvidenceError("release evidence must be a JSON object")
    if type(payload.get("schema_version")) is not int or payload["schema_version"] != 1:
        raise ReleaseEvidenceError("unsupported release evidence schema_version")

    status = _required_string(payload.get("status"), "status")
    if status not in {"ready", "not_ready"}:
        raise ReleaseEvidenceError("status must be ready or not_ready")
    generated_at = _required_string(payload.get("generated_at"), "generated_at")
    _generated_datetime(generated_at)

    repository = payload.get("repository")
    if not isinstance(repository, dict):
        raise ReleaseEvidenceError("repository must be an object")
    branch = _required_string(repository.get("branch"), "repository.branch")
    commit = _required_string(repository.get("commit"), "repository.commit")

    checks = payload.get("checks")
    if not isinstance(checks, list):
        raise ReleaseEvidenceError("checks must be an array")
    parsed_checks = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise ReleaseEvidenceError(f"checks[{index}] must be an object")
        name = _required_string(check.get("name"), f"checks[{index}].name")
        check_status = _required_string(check.get("status"), f"checks[{index}].status")
        if check_status not in VALID_CHECK_STATUSES:
            raise ReleaseEvidenceError(f"checks[{index}].status is invalid")
        mandatory = check.get("mandatory")
        if not isinstance(mandatory, bool):
            raise ReleaseEvidenceError(f"checks[{index}].mandatory must be boolean")
        summary = _required_string(check.get("summary"), f"checks[{index}].summary")
        parsed_checks.append(
            {
                "name": name,
                "status": check_status,
                "mandatory": mandatory,
                "summary": summary,
            }
        )

    return {
        "status": status,
        "generated_at": generated_at,
        "repository": {"branch": branch, "commit": commit},
        "checks": parsed_checks,
        "required_checks": [check for check in parsed_checks if check["mandatory"]],
        "optional_checks": [check for check in parsed_checks if not check["mandatory"]],
    }


class ReleaseEvidenceService:
    """Canonical reader and fail-closed readiness authority for stored evidence."""

    def __init__(
        self,
        repository_root: Path,
        evidence_path: str | Path | None = None,
        max_age_seconds: int = 24 * 60 * 60,
    ) -> None:
        self.path = (
            Path(evidence_path)
            if evidence_path is not None
            else release_evidence_path(repository_root)
        )
        self.max_age = timedelta(seconds=max_age_seconds)

    def load(self, now: datetime | None = None) -> ReleaseEvidenceResult:
        """Read current evidence without creating evidence or rerunning gate logic."""
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ReleaseEvidenceResult(
                None, "Release evidence has not been generated."
            )
        except (OSError, UnicodeError, json.JSONDecodeError):
            return ReleaseEvidenceResult(
                None, "Release evidence could not be read safely."
            )

        try:
            evidence = parse_release_evidence(payload)
            generated_at = _generated_datetime(evidence["generated_at"])
        except ReleaseEvidenceError:
            return ReleaseEvidenceResult(
                None, "Release evidence is malformed or unsupported."
            )

        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        age = current_time.astimezone(timezone.utc) - generated_at
        if age < timedelta(0) or age > self.max_age:
            return ReleaseEvidenceResult(
                None, "Release evidence is stale; readiness cannot be confirmed."
            )
        return ReleaseEvidenceResult(evidence, None)
