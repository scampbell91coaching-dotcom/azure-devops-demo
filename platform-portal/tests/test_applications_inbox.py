from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from portal.extensions import db
from portal import create_app
from portal.models.athlete import Athlete
from portal.models.coaching_application import CoachingApplication
from portal.models.user import User, UserRole


@pytest.fixture
def secured_app():
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": False,
            "SECRET_KEY": "applications-security-test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        athlete_record = Athlete(first_name="Ada", last_name="Athlete", email="ada@example.test")
        db.session.add(athlete_record)
        db.session.flush()
        coach = User(email="coach@example.test", role=UserRole.COACH)
        coach.set_password("coach password secure")
        athlete = User(email="ada@example.test", role=UserRole.ATHLETE, athlete_id=athlete_record.id)
        athlete.set_password("athlete password secure")
        db.session.add_all([coach, athlete])
        db.session.commit()
        app.config["TEST_IDS"] = {"coach": coach.id, "athlete": athlete.id}
    return app


def _sign_in(client, user_id: int, token: str = "applications-csrf") -> str:
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["authenticated_at"] = datetime.now().timestamp()
        session["csrf_token"] = token
    return token


def _application(**overrides) -> CoachingApplication:
    values = {
        "first_name": "Alex",
        "last_name": "Lifter",
        "email": "alex@example.test",
        "instagram": "@alexlifts",
        "country": "United Kingdom",
        "years_training": 4.5,
        "squat_kg": 180,
        "bench_kg": 115,
        "deadlift_kg": 220,
        "next_competition": "Autumn Open",
        "primary_goal": "Qualify for nationals.",
        "biggest_problem": "Managing fatigue.",
        "injury_history": "Previous shoulder irritation.",
        "coaching_expectations": "Direct technical feedback.",
        "video_feedback_ready": True,
        "communication_ready": True,
        "minimum_term_ready": True,
        "privacy_consent": True,
        "status": "new",
    }
    values.update(overrides)
    return CoachingApplication(**values)


def test_coach_can_access_inbox_and_navigation_is_internal(secured_app):
    client = secured_app.test_client()
    _sign_in(client, secured_app.config["TEST_IDS"]["coach"])

    response = client.get("/applications")

    assert response.status_code == 200
    assert 'href="/applications"' in response.get_data(as_text=True)
    assert "traditionalstrength.co.uk/apply" not in response.get_data(as_text=True)


def test_unauthenticated_and_athlete_users_cannot_access_application_data(secured_app):
    anonymous = secured_app.test_client()
    assert anonymous.get("/applications").status_code == 302
    assert anonymous.get("/applications/1").status_code == 302

    athlete = secured_app.test_client()
    _sign_in(athlete, secured_app.config["TEST_IDS"]["athlete"])
    assert athlete.get("/applications").status_code == 403
    assert athlete.get("/applications/1").status_code == 403


def test_inbox_orders_newest_first_and_marks_new_applications(secured_app):
    now = datetime.now()
    with secured_app.app_context():
        db.session.add_all(
            [
                _application(first_name="Older", email="older@example.test", submitted_at=now - timedelta(days=1), status="reviewing"),
                _application(first_name="Newest", email="newest@example.test", submitted_at=now),
            ]
        )
        db.session.commit()

    client = secured_app.test_client()
    _sign_in(client, secured_app.config["TEST_IDS"]["coach"])
    html = client.get("/applications").get_data(as_text=True)

    assert html.index("Newest Lifter") < html.index("Older Lifter")
    assert "New" in html
    assert "new or reviewing" in html


def test_inbox_empty_state(secured_app):
    client = secured_app.test_client()
    _sign_in(client, secured_app.config["TEST_IDS"]["coach"])
    response = client.get("/applications")
    assert response.status_code == 200
    assert b"No applications yet" in response.data


def test_detail_renders_submitted_answers_in_sections(secured_app):
    with secured_app.app_context():
        application = _application()
        db.session.add(application)
        db.session.commit()
        application_id = application.id

    client = secured_app.test_client()
    _sign_in(client, secured_app.config["TEST_IDS"]["coach"])
    response = client.get(f"/applications/{application_id}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    for expected in ("Alex Lifter", "Identity & contact", "Training history", "Goals & challenges", "Qualify for nationals.", "Previous shoulder irritation.", "Direct technical feedback."):
        assert expected in html


def test_invalid_application_id_returns_404(secured_app):
    client = secured_app.test_client()
    _sign_in(client, secured_app.config["TEST_IDS"]["coach"])
    assert client.get("/applications/999999").status_code == 404


def test_coach_can_change_status(secured_app):
    with secured_app.app_context():
        application = _application()
        db.session.add(application)
        db.session.commit()
        application_id = application.id
    client = secured_app.test_client()
    token = _sign_in(client, secured_app.config["TEST_IDS"]["coach"])

    response = client.post(
        f"/applications/{application_id}/status",
        data={"status": "contacted", "csrf_token": token},
    )

    assert response.status_code == 302
    with secured_app.app_context():
        assert db.session.get(CoachingApplication, application_id).status == "contacted"


def test_invalid_status_is_rejected_without_mutation(secured_app):
    with secured_app.app_context():
        application = _application()
        db.session.add(application)
        db.session.commit()
        application_id = application.id
    client = secured_app.test_client()
    token = _sign_in(client, secured_app.config["TEST_IDS"]["coach"])

    response = client.post(f"/applications/{application_id}/status", data={"status": "deleted", "csrf_token": token})

    assert response.status_code == 400
    with secured_app.app_context():
        assert db.session.get(CoachingApplication, application_id).status == "new"


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_status_change_requires_valid_csrf(secured_app, token):
    with secured_app.app_context():
        application = _application()
        db.session.add(application)
        db.session.commit()
        application_id = application.id
    client = secured_app.test_client()
    _sign_in(client, secured_app.config["TEST_IDS"]["coach"])
    data = {"status": "accepted"}
    if token is not None:
        data["csrf_token"] = token

    assert client.post(f"/applications/{application_id}/status", data=data).status_code == 400
    with secured_app.app_context():
        assert db.session.get(CoachingApplication, application_id).status == "new"
