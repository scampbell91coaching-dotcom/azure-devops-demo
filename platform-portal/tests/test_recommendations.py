from datetime import datetime, timezone

from portal import create_app
from portal.extensions import db
from portal.models.platform_snapshot import PlatformSnapshot
from portal.services.recommendations import RecommendationService


def add_snapshot(
    *,
    score: int = 98,
    latency: float = 0.2,
    restarts: int = 0,
    sync: str = "Synced",
    health: str = "Healthy",
    failures: int = 0,
) -> None:
    db.session.add(
        PlatformSnapshot(
            recorded_at=datetime.now(timezone.utc),
            platform_score=score,
            http_status="200",
            health_latency_seconds=latency,
            ready_nodes=2,
            total_nodes=2,
            ready_replicas=2,
            desired_replicas=2,
            container_restarts=restarts,
            argo_sync_status=sync,
            argo_health_status=health,
            security_pass_count=5,
            warning_count=0,
            failure_count=failures,
            git_revision="abc1234",
            git_branch="main",
        )
    )
    db.session.commit()


def create_test_app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def test_recommendation_service_reports_healthy_platform():
    app = create_test_app()

    with app.app_context():
        db.create_all()
        add_snapshot()
        data = RecommendationService().generate(hours=24)

    assert data["status"] == "healthy"
    assert data["summary"]["info"] == 1


def test_recommendation_service_detects_gitops_problem():
    app = create_test_app()

    with app.app_context():
        db.create_all()
        add_snapshot(sync="OutOfSync", health="Degraded")
        data = RecommendationService().generate(hours=24)

    assert data["status"] == "critical"
    assert any(item["category"] == "gitops" for item in data["recommendations"])


def test_recommendations_api_is_available():
    app = create_test_app()

    with app.app_context():
        db.create_all()
        add_snapshot()

    response = app.test_client().get("/api/v1/recommendations")

    assert response.status_code == 200
    assert "recommendations" in response.get_json()


def test_recommendations_page_is_available():
    app = create_test_app()
    response = app.test_client().get("/recommendations")

    assert response.status_code == 200
    assert b"Platform Recommendations" in response.data
