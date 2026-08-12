from portal import create_app
from portal.services.executive_dashboard import ExecutiveDashboardService


class Repository:
    def __init__(self, payload):
        self.payload = payload

    def load(self):
        return self.payload


def current_snapshot():
    return {
        "generated_at": "2026-08-09T12:00:00+00:00",
        "freshness": {"state": "current"},
        "score": 98,
        "summary": {"pass": 3, "warn": 0, "fail": 0},
        "platform": {"nodes_ready": 2, "nodes_total": 2},
        "workload": {"ready_replicas": 2, "desired_replicas": 2, "container_restarts": 0},
        "gitops": {"sync_status": "Synced", "health_status": "Healthy"},
        "availability": {"http_code": "200", "health_latency_seconds": 0.2},
        "git": {"revision": "abc1234", "branch": "main"},
        "checks": [],
    }


def test_executive_service_returns_current_snapshot():
    data = ExecutiveDashboardService(Repository(current_snapshot())).build()
    assert data["latest"]["platform_score"] == 98
    assert data["latest"]["node_readiness"] == "2/2"
    assert data["status"] == "healthy"


def test_executive_service_does_not_present_missing_snapshot_as_healthy():
    payload = {"freshness": {"state": "unavailable"}, "checks": []}
    data = ExecutiveDashboardService(Repository(payload)).build()
    assert data["latest"] is None
    assert data["status"] == "unavailable"


def test_executive_api_is_populated_from_snapshot(monkeypatch):
    service = ExecutiveDashboardService(Repository(current_snapshot()))
    monkeypatch.setattr("portal.api.executive.service", service)
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    response = app.test_client().get("/api/v1/executive")
    assert response.status_code == 200
    assert response.get_json()["latest"]["git_revision"] == "abc1234"


def test_overview_page_contains_executive_dashboard():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert b"executive-score" in response.data


class Snapshot:
    def __init__(self, score, latency, restarts):
        self.platform_score = score
        self.health_latency_seconds = latency
        self.container_restarts = restarts


class SnapshotRepository:
    def list_since(self, hours=24):
        assert hours == 24
        return [
            Snapshot(88, 0.2200, 1),
            Snapshot(91, 0.0895, 0),
        ]


def test_executive_service_calculates_trends_from_history():
    dashboard = ExecutiveDashboardService(
        Repository(current_snapshot()),
        snapshot_repository=SnapshotRepository(),
    ).build(hours=24)

    assert dashboard["trend"] == {
        "score_change": 3,
        "latency_change": -0.1305,
        "restart_change": -1,
    }
