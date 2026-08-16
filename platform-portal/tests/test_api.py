from portal import create_app
from portal.extensions import db
from prometheus_client.parser import text_string_to_metric_families

TEST_CONFIG = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}


def test_health():
    r = create_app(TEST_CONFIG).test_client().get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "healthy"}


def test_liveness_is_process_only_and_readiness_checks_database(monkeypatch):
    app = create_app(TEST_CONFIG)
    client = app.test_client()

    monkeypatch.setattr(
        db.session,
        "execute",
        lambda statement: (_ for _ in ()).throw(RuntimeError("database offline")),
    )

    assert client.get("/live").get_json() == {"status": "alive"}
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.get_json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable"},
    }


def test_metrics_deny_public_access_but_allow_authenticated_internal_scrape():
    app = create_app({**TEST_CONFIG, "AUTHENTICATION_DISABLED": False, "METRICS_BEARER_TOKEN": "monitor-only-secret"})
    client = app.test_client()
    client.get("/missing?secret=not-a-label")
    assert client.get("/metrics").status_code == 404
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 404
    response = client.get("/metrics", headers={"Authorization": "Bearer monitor-only-secret"})

    assert response.status_code == 200
    families = list(text_string_to_metric_families(response.get_data(as_text=True)))
    samples = [sample for family in families for sample in family.samples]
    request_samples = [
        sample for sample in samples if sample.name == "flask_http_requests_total"
    ]
    assert any(
        sample.labels.get("endpoint") == "unmatched" for sample in request_samples
    )
    assert all(
        sample.labels.get("endpoint") != "/metrics" for sample in request_samples
    )
    assert "not-a-label" not in response.get_data(as_text=True)


def test_platform_api():
    r = create_app(TEST_CONFIG).test_client().get("/api/v1/platform")
    assert r.status_code == 200
    assert r.is_json


def test_security_api():
    d = create_app(TEST_CONFIG).test_client().get("/api/v1/security").get_json()
    assert all(k in d for k in ("security", "identity", "checks"))
