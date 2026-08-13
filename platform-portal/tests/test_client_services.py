from datetime import UTC, datetime

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.client_service import ClientServiceChange
from portal.models.user import User, UserRole
from portal.services.client_services import resolved_client_services
from tenancy_factories import grant_coach_athlete_access


@pytest.fixture
def services_app():
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": False,
            "SECRET_KEY": "service-test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        athlete = Athlete(first_name="Alex", last_name="Rivera", email="alex@example.test")
        coach = User(email="coach@example.test", role=UserRole.COACH)
        coach.set_password("correct horse battery staple")
        db.session.add_all([athlete, coach])
        grant_coach_athlete_access(
            coach, [athlete], name="Client Services Strength", slug="client-services-strength"
        )
        db.session.commit()
        app.config["ATHLETE_ID"] = athlete.id
    return app


def _login(client):
    page = client.get("/login")
    token = page.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()
    client.post("/login", data={"email": "coach@example.test", "password": "correct horse battery staple", "csrf_token": token})
    page = client.get("/athletes")
    return page.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()


def test_dashboard_shows_effective_provenance_and_scheduled_change(services_app):
    with services_app.app_context():
        athlete_id = services_app.config["ATHLETE_ID"]
        coach = User.query.filter_by(email="coach@example.test").one()
        db.session.add_all([
            ClientServiceChange(athlete_id=athlete_id, service="nutrition", value="yes", effective_at=datetime(2026, 8, 1), changed_by_user_id=coach.id),
            ClientServiceChange(athlete_id=athlete_id, service="nutrition", value="no", effective_at=datetime(2026, 9, 1), changed_by_user_id=coach.id),
        ])
        db.session.commit()
        state = {item["key"]: item for item in resolved_client_services(athlete_id, now=datetime(2026, 8, 10, tzinfo=UTC))}
        assert state["nutrition"]["value"] == "yes"
        assert state["nutrition"]["provenance"] == "coach@example.test"
        assert state["nutrition"]["scheduled"].value == "no"


def test_coach_can_update_services_without_deleting_history(services_app):
    client = services_app.test_client()
    token = _login(client)
    athlete_id = services_app.config["ATHLETE_ID"]
    response = client.post(
        f"/athletes/{athlete_id}/services",
        data={"csrf_token": token, "training": "no", "nutrition": "yes", "meet_day": "no", "video_review": "limited"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("#client-services")
    with services_app.app_context():
        changes = ClientServiceChange.query.order_by(ClientServiceChange.id).all()
        assert [(item.service, item.value) for item in changes] == [
            ("training", "no"),
            ("video_review", "limited"),
        ]
        assert all(item.changed_by.email == "coach@example.test" for item in changes)

    page = client.get(f"/athletes/{athlete_id}")
    assert b"Existing programmes, check-ins, reviews and notes are retained" in page.data
    assert b"Set by coach@example.test" in page.data


def test_invalid_service_value_is_rejected(services_app):
    client = services_app.test_client()
    token = _login(client)
    response = client.post(
        f"/athletes/{services_app.config['ATHLETE_ID']}/services",
        data={"csrf_token": token, "training": "maybe", "nutrition": "no", "meet_day": "no", "video_review": "none"},
    )
    assert response.status_code == 400
