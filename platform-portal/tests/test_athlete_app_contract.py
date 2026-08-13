from __future__ import annotations

import time
from datetime import date

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings
from portal.models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from portal.models.user import User, UserRole


def _app():
    return create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": False,
            "SECRET_KEY": "athlete-app-contract-test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def _seed(app):
    with app.app_context():
        athlete = Athlete(first_name="Ada", last_name="Lifter", email="ada@app.test")
        other = Athlete(first_name="Bea", last_name="Lifter", email="bea@app.test")
        db.session.add_all([athlete, other])
        db.session.flush()
        user = User(email=athlete.email, role=UserRole.ATHLETE, athlete_id=athlete.id)
        coach = User(email="coach@app.test", role=UserRole.COACH)
        block = TrainingBlock(athlete_id=athlete.id, name="Powerlifting peak", status="active")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        training_session = TrainingSession(week=week, name="Squat", position=1)
        prescription = ExercisePrescription(
            session=training_session,
            exercise_name="Competition squat",
            position=1,
            sets=1,
            reps="3",
            rpe=8,
        )
        private_block = TrainingBlock(athlete_id=other.id, name="Private", status="active")
        private_week = TrainingWeek(block=private_block, name="Private week", position=1)
        private_session = TrainingSession(week=private_week, name="Private deadlift", position=1)
        db.session.add_all(
            [
                user,
                coach,
                block,
                prescription,
                private_block,
                private_session,
                AthleteCheckinSettings(
                    athlete=athlete,
                    training_enabled=True,
                    nutrition_enabled=False,
                    workflow_active=True,
                    checkin_day=0,
                ),
            ]
        )
        db.session.commit()
        return {
            "user": user.id,
            "coach": coach.id,
            "athlete": athlete.id,
            "session": training_session.id,
            "prescription": prescription.id,
            "private_session": private_session.id,
        }


def _authenticate(client, user_id):
    with client.session_transaction() as auth_session:
        auth_session["user_id"] = user_id
        auth_session["authenticated_at"] = time.time()
        auth_session["csrf_token"] = "test-csrf-token"


def test_contract_is_versioned_and_programme_is_self_scoped():
    app = _app()
    ids = _seed(app)
    client = app.test_client()
    _authenticate(client, ids["user"])

    response = client.get("/api/athlete/v1/programme")

    assert response.status_code == 200
    assert response.json["contract_version"] == "athlete.v1"
    assert response.json["data"]["name"] == "Powerlifting peak"
    assert "athlete_id" not in response.get_data(as_text=True)
    assert client.get(
        f"/api/athlete/v1/programme/sessions/{ids['private_session']}"
    ).status_code == 404


def test_session_logging_delegates_to_existing_completion_rules():
    app = _app()
    ids = _seed(app)
    client = app.test_client()
    _authenticate(client, ids["user"])
    path = f"/api/athlete/v1/programme/sessions/{ids['session']}/log"
    headers = {"X-CSRF-Token": "test-csrf-token"}

    response = client.put(
        path,
        json={
            "intent": "finish",
            "sets": [
                {
                    "prescription_id": ids["prescription"],
                    "order": 1,
                    "completed": True,
                    "load_kg": 180,
                    "reps": 3,
                    "rpe": 8,
                }
            ],
        },
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json["data"]["log"]["status"] == "completed"
    replay = client.put(path, json={"intent": "save", "sets": []}, headers=headers)
    assert replay.status_code == 422
    assert replay.json["data"]["errors"] == ["Completed sessions are read-only."]


def test_checkin_creation_uses_existing_validation_and_returns_receipt():
    app = _app()
    ids = _seed(app)
    client = app.test_client()
    _authenticate(client, ids["user"])
    payload = {
        "week_ending": date(2026, 8, 9).isoformat(),
        "training_adherence": 90,
        "fatigue": 6,
        "recovery": 7,
        "motivation": 8,
        "sleep_quality": 7,
        "stress": 4,
        "pain_present": False,
        "training_notes": "Squat moved well.",
    }

    response = client.post(
        "/api/athlete/v1/check-ins",
        json=payload,
        headers={"X-CSRF-Token": "test-csrf-token"},
    )

    assert response.status_code == 201
    assert response.json["contract_version"] == "athlete.v1"
    assert response.json["data"]["training"]["notes"] == "Squat moved well."
    duplicate = client.post(
        "/api/athlete/v1/check-ins",
        json=payload,
        headers={"X-CSRF-Token": "test-csrf-token"},
    )
    assert duplicate.status_code == 422
    assert "week_ending" in duplicate.json["data"]["errors"]


def test_api_rejects_anonymous_and_coach_identities():
    app = _app()
    ids = _seed(app)
    client = app.test_client()

    assert client.get("/api/athlete/v1/today").status_code == 401
    _authenticate(client, ids["coach"])
    assert client.get("/api/athlete/v1/today").status_code == 403


def test_empty_nutrition_plan_is_explicitly_null():
    app = _app()
    ids = _seed(app)
    client = app.test_client()
    _authenticate(client, ids["user"])

    response = client.get("/api/athlete/v1/nutrition/plan")

    assert response.status_code == 200
    assert response.json == {"contract_version": "athlete.v1", "data": None}
