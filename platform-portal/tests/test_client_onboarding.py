from datetime import UTC, datetime, timedelta

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.account_token import AccountToken
from portal.models.athlete_state import AthleteStateFact
from portal.models.client_service import ClientServiceChange
from portal.models.checkins import AthleteCheckinSettings
from portal.models.programming import TrainingBlock
from portal.models.user import User, UserRole
from portal.services.transactional_email import MemoryEmailTransport
from portal.services.client_onboarding import build_client_onboarding


@pytest.fixture
def onboarding_app():
    transport = MemoryEmailTransport()
    app = create_app({
        "TESTING": True,
        "AUTHENTICATION_DISABLED": False,
        "SECRET_KEY": "onboarding-test-key",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "EMAIL_TRANSPORT": transport,
        "ACCOUNT_PUBLIC_BASE_URL": "https://athletes.example.test",
    })
    with app.app_context():
        db.create_all()
        coach = User(email="coach@example.test", role=UserRole.COACH)
        coach.set_password("correct horse battery staple")
        athlete = Athlete(first_name="Sam", last_name="Strong", email="sam@example.test")
        db.session.add_all([coach, athlete])
        db.session.commit()
        app.config["ATHLETE_ID"] = athlete.id
    app.config["TEST_TRANSPORT"] = transport
    return app


def _csrf(client, path="/login"):
    response = client.get(path)
    return response.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()


def _login(client):
    return client.post("/login", data={
        "email": "coach@example.test",
        "password": "correct horse battery staple",
        "csrf_token": _csrf(client),
    })


def _session_csrf(client, page):
    return _csrf(client, page)


def test_onboarding_enforces_order_and_is_coach_only(onboarding_app):
    athlete_id = onboarding_app.config["ATHLETE_ID"]
    anonymous = onboarding_app.test_client()
    assert anonymous.get(f"/athletes/{athlete_id}/onboarding").status_code == 302

    client = onboarding_app.test_client()
    _login(client)
    page = f"/athletes/{athlete_id}/onboarding"
    response = client.get(page)
    assert response.status_code == 200
    assert b'aria-current="step"' in response.data
    assert b"Issue invitation" in response.data

    response = client.post(
        f"{page}/goals",
        data={
            "csrf_token": _session_csrf(client, page),
            "primary_goal": "Total 600 kg",
            "success_definition": "Qualify for nationals",
        },
    )
    assert response.status_code == 409
    with onboarding_app.app_context():
        assert AthleteStateFact.query.count() == 0


def test_complete_guided_onboarding_reaches_ready_without_schema_changes(onboarding_app):
    client = onboarding_app.test_client()
    _login(client)
    athlete_id = onboarding_app.config["ATHLETE_ID"]
    page = f"/athletes/{athlete_id}/onboarding"

    response = client.post(
        f"{page}/invite", data={"csrf_token": _session_csrf(client, page)}
    )
    assert response.status_code == 302
    assert len(onboarding_app.config["TEST_TRANSPORT"].messages) == 1

    body = onboarding_app.config["TEST_TRANSPORT"].messages[0].get_content()
    activation_url = body.split("https://athletes.example.test", 1)[1].split()[0]
    activation_path, raw_token = activation_url.split("#", 1)
    account_csrf = _csrf(client, activation_path)
    response = client.post(activation_path, data={
        "csrf_token": account_csrf,
        "account_token": raw_token,
        "password": "a sufficiently secure password",
        "password_confirmation": "a sufficiently secure password",
    })
    assert response.status_code == 302

    # Activation signs in as the athlete. Start a fresh coach session.
    with client.session_transaction() as session:
        session.clear()
    _login(client)

    response = client.post(f"{page}/goals", data={
        "csrf_token": _session_csrf(client, page),
        "primary_goal": "Build a 600 kg total",
        "success_definition": "Qualify for nationals without missed training",
    })
    assert response.status_code == 302

    response = client.post(f"{page}/services", data={
        "csrf_token": _session_csrf(client, page),
        "training": "yes", "nutrition": "yes", "meet_day": "no",
        "video_review": "limited",
    })
    assert response.status_code == 302

    with onboarding_app.app_context():
        block = TrainingBlock(
            athlete_id=athlete_id, name="Foundation block", objective="Build work capacity"
        )
        db.session.add(block)
        db.session.commit()
        block_id = block.id

    response = client.post(f"{page}/programme", data={
        "csrf_token": _session_csrf(client, page), "block_id": str(block_id),
    })
    assert response.status_code == 302

    response = client.post(f"{page}/check-in", data={
        "csrf_token": _session_csrf(client, page),
        "training_enabled": "1", "nutrition_enabled": "1", "checkin_day": "4",
    })
    assert response.status_code == 302
    ready = client.get(page)
    assert ready.status_code == 200
    assert b"Sam is ready to start" in ready.data

    with onboarding_app.app_context():
        assert db.session.get(TrainingBlock, block_id).status == "active"
        settings = AthleteCheckinSettings.query.filter_by(athlete_id=athlete_id).one()
        assert settings.workflow_active is True
        assert settings.training_enabled is True
        assert settings.nutrition_enabled is True
        assert settings.checkin_day == 4
        facts = {item.fact_type: item.value_json for item in AthleteStateFact.query.all()}
        assert facts["onboarding_goals"]["primary_goal"] == "Build a 600 kg total"
        assert facts["onboarding_services"]["video_review"] == "limited"
        assert facts["onboarding_checkin_setup"]["checkin_day"] == 4


def test_non_training_entitlement_skips_programme_step(onboarding_app):
    with onboarding_app.app_context():
        athlete = db.session.get(Athlete, onboarding_app.config["ATHLETE_ID"])
        user = User(email=athlete.email, role=UserRole.ATHLETE, athlete_id=athlete.id)
        user.set_password("a sufficiently secure password")
        db.session.add(user)
        db.session.flush()
        now = datetime.now(UTC).replace(tzinfo=None)
        db.session.add(AccountToken(
            purpose="invitation", token_digest="a" * 64, athlete_id=athlete.id,
            user_id=user.id, expires_at=now + timedelta(hours=1), consumed_at=now,
        ))
        db.session.add_all([
            AthleteStateFact(
                athlete_id=athlete.id, fact_type="onboarding_goals",
                value_json={"primary_goal": "Nutrition consistency", "success_definition": "Hit targets"},
                source_type="coach",
            ),
            AthleteStateFact(
                athlete_id=athlete.id, fact_type="onboarding_services",
                value_json={"training": "no", "nutrition": "yes"}, source_type="coach",
            ),
            ClientServiceChange(
                athlete_id=athlete.id, service="training", value="no", effective_at=now,
            ),
            ClientServiceChange(
                athlete_id=athlete.id, service="nutrition", value="yes", effective_at=now,
            ),
        ])
        db.session.commit()
        onboarding = build_client_onboarding(athlete)
        assert onboarding.current_step == "checkin"
        assert onboarding.active_programme is None
        assert next(step for step in onboarding.steps if step.key == "programme").complete is True
