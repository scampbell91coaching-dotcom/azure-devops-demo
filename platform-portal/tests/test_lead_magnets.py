from portal import create_app
from portal.extensions import db
from portal.models.lead_capture import LeadCapture


def create_test_app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def test_hip_pain_lead_magnet_page():
    app = create_test_app()
    response = app.test_client().get("/guides/hip-pain")

    assert response.status_code == 200
    assert b"Hip Pain Guide" in response.data


def test_unknown_lead_magnet_returns_404():
    app = create_test_app()
    response = app.test_client().get("/guides/not-real")

    assert response.status_code == 404


def test_lead_capture_is_persisted():
    app = create_test_app()

    with app.app_context():
        db.create_all()

    response = app.test_client().post(
        "/api/v1/lead-captures",
        data={
            "first_name": "Steve",
            "email": "steve@example.com",
            "source_slug": "hip-pain",
            "consent": "on",
        },
    )

    assert response.status_code == 302

    with app.app_context():
        lead = LeadCapture.query.one()
        assert lead.email == "steve@example.com"
        assert lead.source_slug == "hip-pain"
        assert lead.consent is True
