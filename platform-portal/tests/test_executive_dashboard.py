from datetime import datetime, timezone

from portal import create_app
from portal.extensions import db
from portal.models.platform_snapshot import PlatformSnapshot
from portal.services.executive_dashboard import ExecutiveDashboardService


def create_test_app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def add_snapshot(score: int = 98) -> None:
    db.session.add(
        PlatformSnapshot(
            recorded_at=datetime.now(timezone.utc),
            platform_score=score,
            http_status="200",
            health_latency_seconds=0.2,
            ready_nodes=2,
            total_nodes=2,
            ready_replicas=2,
            desired_replicas=2,
            container_restarts=0,
            argo_sync_status="Synced",
            argo_health_status="Healthy",
            security_pass_count=5,
            warning_count=0,
            failure_count=0,
            git_revision="abc1234",
            git_branch="main",
        )
    )
    db.session.commit()


def test_executive_service_returns_latest_snapshot():
    app = create_test_app()

    with app.app_context():
        db.create_all()
        add_snapshot()
        data = ExecutiveDashboardService().build(hours=24)

    assert data["latest"]["platform_score"] == 98
    assert data["latest"]["node_readiness"] == "2/2"
    assert data["status"] == "healthy"


def test_executive_api_is_available():
    app = create_test_app()

    with app.app_context():
        db.create_all()
        add_snapshot()

    response = app.test_client().get("/api/v1/executive")

    assert response.status_code == 200
    assert response.get_json()["latest"]["git_revision"] == "abc1234"


def test_overview_page_contains_executive_dashboard():
    app = create_test_app()
    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"Traditional Strength Platform" in response.data
    assert b"executive-score" in response.data
