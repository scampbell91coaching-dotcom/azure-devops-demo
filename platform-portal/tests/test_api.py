from portal import create_app

TEST_CONFIG = {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}


def test_health():
    r = create_app(TEST_CONFIG).test_client().get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "healthy"}


def test_platform_api():
    r = create_app(TEST_CONFIG).test_client().get("/api/v1/platform")
    assert r.status_code == 200
    assert r.is_json


def test_security_api():
    d = create_app(TEST_CONFIG).test_client().get("/api/v1/security").get_json()
    assert all(k in d for k in ("security", "identity", "checks"))
