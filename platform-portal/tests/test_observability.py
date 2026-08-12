import json
from datetime import datetime, timezone

from portal import create_app
from portal.repositories.status_repository import JsonStatusRepository
from portal.services.platform_status import PlatformStatusService


class Repository:
    def __init__(self, payload):
        self.payload = payload
        self.loads = 0

    def load(self):
        self.loads += 1
        return self.payload


def service_for(payload):
    repository = Repository(payload)
    return PlatformStatusService(repository), repository


def test_complete_observability_payload_and_controls():
    service, repository = service_for(
        {
            "generated_at": "2026-08-08T12:00:00+00:00",
            "observability": {
                "metrics_api_available": True,
                "service_monitor_present": True,
            },
            "availability": {
                "http_code": "200",
                "health_latency_seconds": 0.125,
            },
            "checks": [
                {
                    "area": "Observability",
                    "name": "Metrics API",
                    "status": "PASS",
                    "detail": "Available",
                },
                {
                    "area": "Security",
                    "name": "Seccomp",
                    "status": "PASS",
                    "detail": "Enabled",
                },
            ],
        }
    )

    result = service.observability_status()

    assert repository.loads == 1
    assert result["telemetry"] == {
        "metrics_api": {"status": "AVAILABLE", "value": True},
        "service_monitor": {"status": "AVAILABLE", "value": True},
        "health": {"status": "AVAILABLE", "http_code": "200"},
        "latency_sample": {"status": "AVAILABLE", "seconds": 0.125},
    }
    assert [control["name"] for control in result["controls"]] == ["Metrics API"]


def test_missing_and_partial_telemetry_remains_unknown_or_not_configured():
    service, _ = service_for(
        {
            "observability": {"service_monitor_present": False},
            "availability": {"http_code": "503", "health_latency_seconds": 1.2},
            "checks": [],
        }
    )

    telemetry = service.observability_status()["telemetry"]

    assert telemetry["metrics_api"] == {"status": "UNKNOWN", "value": None}
    assert telemetry["service_monitor"] == {"status": "NOT_CONFIGURED", "value": False}
    assert telemetry["health"] == {"status": "UNAVAILABLE", "http_code": "503"}
    assert telemetry["latency_sample"] == {"status": "DEGRADED", "seconds": 1.2}


def test_malformed_optional_fields_are_safe():
    service, _ = service_for(
        {
            "observability": "invalid",
            "availability": {"http_code": {}, "health_latency_seconds": "fast"},
            "checks": [None, "invalid", {"area": "Observability"}],
        }
    )

    result = service.observability_status()

    assert all(item["status"] == "UNKNOWN" for item in result["telemetry"].values())
    assert result["controls"] == [
        {
            "area": "Observability",
            "name": "Not reported",
            "status": "UNKNOWN",
            "detail": "Not reported",
        }
    ]


def test_collector_freshness_is_exposed_for_current_stale_and_unavailable():
    for state in ("current", "stale", "unavailable"):
        service, _ = service_for({"freshness": {"state": state}})
        assert service.observability_status()["freshness"]["state"] == state


def test_repository_error_control_is_not_hidden():
    service, _ = service_for(
        {
            "checks": [
                {
                    "area": "Portal",
                    "name": "Status data",
                    "status": "FAIL",
                    "detail": "Unable to read status data",
                }
            ]
        }
    )

    result = service.observability_status()

    assert result["controls"][0]["status"] == "FAIL"
    assert result["telemetry"]["metrics_api"]["status"] == "UNKNOWN"


def test_observability_api_uses_stable_contract(monkeypatch):
    payload = {"telemetry": {}, "controls": [], "generated_at": None}
    monkeypatch.setattr(
        "portal.api.platform.service.observability_status", lambda: payload
    )
    client = create_app(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}
    ).test_client()

    response = client.get("/api/v1/observability")

    assert response.status_code == 200
    assert response.get_json() == payload


def test_observability_api_is_populated_from_configured_file(tmp_path, monkeypatch):
    path = tmp_path / "platform-status.json"
    path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "observability": {"metrics_api_available": True, "service_monitor_present": False},
        "availability": {"http_code": "200", "health_latency_seconds": 0.1},
        "checks": [{"area": "Observability", "name": "Metrics API", "status": "PASS", "detail": "Available"}],
    }), encoding="utf-8")
    service = PlatformStatusService(JsonStatusRepository(path))
    monkeypatch.setattr("portal.api.platform.service", service)
    client = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}).test_client()

    payload = client.get("/api/v1/observability").get_json()
    assert payload["freshness"]["state"] == "current"
    assert payload["telemetry"]["metrics_api"]["status"] == "AVAILABLE"
    assert payload["controls"][0]["name"] == "Metrics API"
