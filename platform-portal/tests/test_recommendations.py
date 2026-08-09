from portal import create_app
from portal.services.recommendations import RecommendationService


class Repository:
    def __init__(self, payload):
        self.payload = payload

    def load(self):
        return self.payload


def test_recommendations_are_derived_from_failed_and_warning_checks_only():
    service = RecommendationService(Repository({
        "generated_at": "2026-08-09T12:00:00+00:00",
        "freshness": {"state": "current"},
        "checks": [
            {"area": "GitOps", "name": "Argo CD", "status": "FAIL", "detail": "OutOfSync"},
            {"area": "Observability", "name": "ServiceMonitor", "status": "WARN", "detail": "Missing"},
            {"area": "Workload", "name": "Readiness", "status": "PASS", "detail": "2/2"},
        ],
    }))
    data = service.generate()

    assert data["status"] == "critical"
    assert [item["title"] for item in data["recommendations"]] == [
        "Argo CD requires attention", "ServiceMonitor requires attention"
    ]
    assert data["summary"] == {"critical": 1, "warning": 1, "info": 0}


def test_no_generic_recommendation_when_snapshot_has_no_evidence():
    data = RecommendationService(Repository({
        "freshness": {"state": "current"},
        "checks": [{"area": "Workload", "name": "Readiness", "status": "PASS"}],
    })).generate()

    assert data["status"] == "healthy"
    assert data["recommendations"] == []


def test_stale_snapshot_is_never_healthy():
    data = RecommendationService(Repository({
        "freshness": {"state": "stale", "age_seconds": 901}, "checks": []
    })).generate()

    assert data["status"] == "warning"
    assert data["recommendations"][0]["category"] == "data"


def test_recommendations_api_uses_snapshot_service(monkeypatch):
    payload = {"status": "warning", "recommendations": [], "summary": {}}
    monkeypatch.setattr("portal.api.recommendations.service.generate", lambda hours: payload)
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    response = app.test_client().get("/api/v1/recommendations")
    assert response.status_code == 200
    assert response.get_json() == payload


def test_recommendations_page_is_available():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    response = app.test_client().get("/recommendations")
    assert response.status_code == 200
    assert b"Platform Recommendations" in response.data
