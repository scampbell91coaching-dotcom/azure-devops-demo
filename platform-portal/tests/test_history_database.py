from portal import create_app
from portal.extensions import db
from portal.models.platform_snapshot import PlatformSnapshot
from portal.services.snapshot_ingestion import SnapshotIngestionService


def sample_status():
    return {
        "score": 97,
        "availability": {"http_code": "200", "health_latency_seconds": 0.24},
        "platform": {"nodes_ready": 2, "nodes_total": 2},
        "workload": {
            "ready_replicas": 2,
            "desired_replicas": 2,
            "container_restarts": 0,
        },
        "gitops": {"sync_status": "Synced", "health_status": "Healthy"},
        "summary": {"warn": 1, "fail": 0},
        "git": {"revision": "abc1234", "branch": "main"},
        "checks": [
            {"area": "Security", "status": "PASS"},
            {"area": "Identity", "status": "PASS"},
        ],
    }


def test_snapshot_ingestion_persists_row():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        snapshot = SnapshotIngestionService().ingest(sample_status())
        assert snapshot.id is not None
        assert PlatformSnapshot.query.count() == 1
        assert snapshot.platform_score == 97


def test_history_api_returns_snapshot():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        SnapshotIngestionService().ingest(sample_status())

    response = app.test_client().get("/api/v1/history")
    assert response.status_code == 200
    assert len(response.get_json()["items"]) == 1


def test_history_chart_contract():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        SnapshotIngestionService().ingest(sample_status())

    data = app.test_client().get("/api/v1/history/chart?hours=24").get_json()
    assert data["score"] == [97]
    assert data["latency"] == [0.24]
