from datetime import datetime, timezone
import json

from portal import create_app
from portal.services.engineering_overview import EngineeringOverviewService
from portal.services.release_readiness import ReleaseEvidenceService


class StubStatusService:
    def __init__(self, data):
        self.data = data

    def get_status(self):
        return self.data


def test_adapter_reuses_live_platform_and_release_evidence(tmp_path, monkeypatch):
    evidence = tmp_path / "release-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "ready",
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "repository": {"branch": "main", "commit": "abc123"},
                "checks": [
                    {
                        "name": "pytest",
                        "status": "pass",
                        "mandatory": True,
                        "summary": "tests passed",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    status = StubStatusService(
        {
            "generated_at": "2026-08-04T11:00:00Z",
            "availability": {"http_code": "200"},
            "security": {
                "run_as_non_root": True,
                "privilege_escalation_disabled": True,
                "seccomp_runtime_default": True,
            },
            "gitops": {"sync_status": "Synced", "health_status": "Healthy"},
        }
    )
    monkeypatch.setattr(
        "portal.services.engineering_overview.shutil.which",
        lambda tool: f"/bin/{tool}" if tool == "git" else None,
    )

    release_service = ReleaseEvidenceService(tmp_path, evidence)
    result = EngineeringOverviewService(status, release_service).build()

    assert result["health"]["label"] == "Healthy"
    assert result["security"]["state"] == "available"
    assert result["gitops"]["label"] == "Synced / Healthy"
    assert result["release"]["label"] == "Ready"
    assert result["toolchain"][0]["label"] == "Available"
    assert result["toolchain"][1]["label"] == "Unavailable"


def test_adapter_labels_missing_sources_unavailable(tmp_path):
    result = EngineeringOverviewService(
        StubStatusService({"checks": [{"status": "FAIL"}]}),
        ReleaseEvidenceService(tmp_path, tmp_path / "missing.json"),
    ).build()

    assert result["generated_at"] is None
    assert result["health"]["label"] == "Unavailable"
    assert result["security"]["label"] == "Unavailable"
    assert result["gitops"]["label"] == "Unavailable"
    assert result["release"]["label"] == "Not ready"


def test_adapter_rejects_unexpected_source_shapes(tmp_path):
    evidence = tmp_path / "release-evidence.json"
    evidence.write_text("[]", encoding="utf-8")

    result = EngineeringOverviewService(
        StubStatusService([]), ReleaseEvidenceService(tmp_path, evidence)
    ).build()

    assert result["health"]["state"] == "unavailable"
    assert result["release"]["readiness"] == "not_ready"
    assert (
        result["release"]["detail"] == "Release evidence is malformed or unsupported."
    )


def test_engineering_route_and_api_explain_data_boundaries(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "RELEASE_EVIDENCE_FILE": str(tmp_path / "missing.json"),
        }
    )

    page = app.test_client().get("/engineering")
    api = app.test_client().get("/api/v1/engineering-overview")

    assert page.status_code == 200
    assert b"Engineering overview" in page.data
    assert b"Live data unavailable" in page.data
    assert b"Portal host only" in page.data
    assert api.status_code == 200
    assert api.get_json()["release"]["state"] == "unavailable"
