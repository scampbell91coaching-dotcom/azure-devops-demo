from portal.extensions import db
from portal.models.lead_capture import LeadCapture
from public_app import create_public_app


def create_test_app():
    return create_public_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def test_public_app_only_exposes_public_routes():
    app = create_test_app()
    client = app.test_client()

    assert client.get("/health").status_code == 200
    assert client.get("/guides/hip-pain").status_code == 200
    assert client.get("/guides/shoulder-pain").status_code == 200
    assert client.get("/history").status_code == 404
    assert client.get("/recommendations").status_code == 404
    assert client.get("/api/v1/executive").status_code == 404


def test_public_lead_capture_persists():
    app = create_test_app()

    with app.app_context():
        db.create_all()

    response = app.test_client().post(
        "/api/v1/lead-captures",
        data={
            "first_name": "Steve",
            "email": "steve@example.com",
            "source_slug": "shoulder-pain",
            "consent": "on",
        },
    )

    assert response.status_code == 302

    with app.app_context():
        assert LeadCapture.query.count() == 1
