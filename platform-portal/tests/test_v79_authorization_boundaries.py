from __future__ import annotations

import time

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings
from portal.models.programming import TrainingBlock, TrainingSession, TrainingWeek
from portal.models.user import User, UserRole


@pytest.fixture
def secured_delivery_app():
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": False,
            "SECRET_KEY": "v79-authorization-boundaries",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        owner = Athlete(first_name="Owner", last_name="Athlete", email="owner@example.test")
        other = Athlete(first_name="Other", last_name="Athlete", email="other@example.test")
        block = TrainingBlock(athlete=owner, name="Owned block")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        training_session = TrainingSession(week=week, name="Session 1", position=1)
        db.session.add_all([owner, other, block])
        db.session.flush()
        coach = User(email="coach@example.test", role=UserRole.COACH, password_hash="unused")
        owner_user = User(
            email=owner.email,
            role=UserRole.ATHLETE,
            athlete_id=owner.id,
            password_hash="unused",
        )
        other_user = User(
            email=other.email,
            role=UserRole.ATHLETE,
            athlete_id=other.id,
            password_hash="unused",
        )
        db.session.add_all(
            [
                coach,
                owner_user,
                other_user,
                AthleteCheckinSettings(
                    athlete=owner,
                    training_enabled=True,
                    nutrition_enabled=True,
                    workflow_active=True,
                ),
                AthleteCheckinSettings(
                    athlete=other,
                    training_enabled=True,
                    nutrition_enabled=True,
                    workflow_active=True,
                ),
            ]
        )
        db.session.commit()
        app.config["DELIVERY_IDS"] = {
            "owner": owner.id,
            "other": other.id,
            "coach": coach.id,
            "owner_user": owner_user.id,
            "other_user": other_user.id,
            "session": training_session.id,
        }
    return app


def _sign_in(client, user_id: int, csrf: str = "v79-valid-csrf") -> str:
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["authenticated_at"] = time.time()
        session["csrf_token"] = csrf
    return csrf


def test_athlete_can_access_own_nutrition_import_mutation_surface(
    secured_delivery_app,
):
    ids = secured_delivery_app.config["DELIVERY_IDS"]
    client = secured_delivery_app.test_client()
    csrf = _sign_in(client, ids["owner_user"])

    preview = client.post(
        f"/athletes/{ids['owner']}/nutrition-import/preview",
        data={"csrf_token": csrf},
    )
    assert preview.status_code == 400

    disconnect = client.post(
        f"/athletes/{ids['owner']}/nutrition-import/disconnect",
        data={"csrf_token": csrf},
    )
    assert disconnect.status_code == 302


def test_athlete_cannot_access_another_athletes_nutrition_import_mutations(
    secured_delivery_app,
):
    ids = secured_delivery_app.config["DELIVERY_IDS"]
    client = secured_delivery_app.test_client()
    csrf = _sign_in(client, ids["owner_user"])

    response = client.post(
        f"/athletes/{ids['other']}/nutrition-import/preview",
        data={"csrf_token": csrf},
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("path", "data"),
    [
        (
            "/programming/sessions/{session}/warmup-assignments",
            {"protocol_id": "1", "reason": "test"},
        ),
        (
            "/programming/sessions/{session}/warmup-overrides",
            {"action": "remove", "target_key": "x", "reason": "test"},
        ),
        (
            "/programming/sessions/{session}/warmup-candidates/override",
            {"protocol_id": "1", "action": "remove", "reason": "test"},
        ),
        ("/programming/factory/preview", {"athlete_id": "1"}),
        (
            "/programming/factory",
            {"proposal_id": "1", "proposal_integrity": "x"},
        ),
    ],
)
def test_athlete_cannot_invoke_coaching_delivery_mutations(
    secured_delivery_app, path, data
):
    ids = secured_delivery_app.config["DELIVERY_IDS"]
    client = secured_delivery_app.test_client()
    csrf = _sign_in(client, ids["owner_user"])
    payload = {**data, "csrf_token": csrf}

    response = client.post(path.format(**ids), data=payload)

    assert response.status_code == 403

def test_athlete_nutrition_read_is_owned_and_does_not_trust_path_identity(
    secured_delivery_app,
):
    ids = secured_delivery_app.config["DELIVERY_IDS"]
    client = secured_delivery_app.test_client()
    _sign_in(client, ids["owner_user"])

    assert client.get(f"/athletes/{ids['owner']}/nutrition-import").status_code == 200
    assert client.get(f"/athletes/{ids['other']}/nutrition-import").status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/athletes/{owner}/nutrition-import/preview",
        "/programming/sessions/{session}/warmup-assignments",
        "/programming/sessions/{session}/warmup-candidates/override",
        "/programming/factory/preview",
    ],
)
def test_coach_delivery_mutations_require_csrf(secured_delivery_app, path):
    ids = secured_delivery_app.config["DELIVERY_IDS"]
    client = secured_delivery_app.test_client()
    _sign_in(client, ids["coach"])

    response = client.post(path.format(**ids), data={})

    assert response.status_code == 400
    assert b"Invalid CSRF token" in response.data
