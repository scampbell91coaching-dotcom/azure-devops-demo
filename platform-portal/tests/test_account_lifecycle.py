from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.account_token import AccountToken, AccountTokenPurpose
from portal.models.athlete import Athlete
from portal.models.user import User, UserRole
from portal.services.account_lifecycle import digest_token
from portal.services.transactional_email import MemoryEmailTransport


class FailingTransport:
    def send(self, _message):
        raise RuntimeError("provider unavailable")


@pytest.fixture
def lifecycle_app():
    transport = MemoryEmailTransport()
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": False,
            "SECRET_KEY": "account-test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "EMAIL_TRANSPORT": transport,
            "ACCOUNT_PUBLIC_BASE_URL": "https://athletes.example.test",
        }
    )
    with app.app_context():
        db.create_all()
        athlete = Athlete(first_name="New", last_name="Athlete", email="new@example.test")
        other = Athlete(first_name="Other", last_name="Athlete", email="other@example.test")
        coach = User(email="coach@example.test", role=UserRole.COACH)
        coach.set_password("correct horse battery staple")
        db.session.add_all([athlete, other, coach])
        db.session.commit()
        app.config["IDS"] = {"athlete": athlete.id, "other": other.id}
    app.config["TEST_TRANSPORT"] = transport
    return app


def csrf(client) -> str:
    response = client.get("/login")
    return response.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()


def login_coach(client):
    return client.post(
        "/login",
        data={
            "email": "coach@example.test",
            "password": "correct horse battery staple",
            "csrf_token": csrf(client),
        },
    )


def invitation(client, app, email="new@example.test"):
    athlete_id = app.config["IDS"]["athlete"]
    response = client.post(
        f"/athletes/{athlete_id}/account/invite",
        data={"csrf_token": csrf_from_session(client), "email": email},
    )
    with app.app_context():
        record = AccountToken.query.filter_by(purpose="invitation").order_by(AccountToken.id.desc()).first()
        record_id = record.id if record else None
    return response, record_id


def csrf_from_session(client):
    with client.session_transaction() as auth_session:
        token = auth_session.get("csrf_token")
    if token is None:
        response = client.get("/athletes")
        token = response.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()
    return token


def raw_token_from_message(app, index=-1):
    body = app.config["TEST_TRANSPORT"].messages[index].get_content()
    return body.split("/account/invitation#", 1)[1].split()[0]


def submit_password(client, path, password="a sufficiently secure password"):
    request_path, raw_token = path.split("#", 1)
    page = client.get(request_path)
    token = page.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()
    return client.post(
        request_path,
        data={"csrf_token": token, "account_token": raw_token, "password": password, "password_confirmation": password},
    )


def test_invitation_creation_sender_configured_success_and_digest_storage(lifecycle_app):
    client = lifecycle_app.test_client()
    login_coach(client)
    response, record_id = invitation(client, lifecycle_app)

    assert response.status_code == 200
    assert b"Email accepted for delivery" in response.data
    message = lifecycle_app.config["TEST_TRANSPORT"].messages[0]
    assert message["From"] == "Traditional Strength <coach@traditionalstrength.co.uk>"
    assert message["To"] == "new@example.test"
    raw = raw_token_from_message(lifecycle_app)
    assert len(raw) >= 43
    with lifecycle_app.app_context():
        record = db.session.get(AccountToken, record_id)
        assert record.delivery_state == "sent"
        assert record.token_digest == digest_token(raw)
        assert raw not in record.token_digest
        user = User.query.filter_by(athlete_id=lifecycle_app.config["IDS"]["athlete"]).one()
        assert user.active is False and user.password_hash is None


@pytest.mark.parametrize("transport,state", [(None, "not_configured"), (FailingTransport(), "failed")])
def test_delivery_failure_states_surface_secure_manual_fallback(lifecycle_app, transport, state):
    lifecycle_app.config["EMAIL_TRANSPORT"] = transport
    client = lifecycle_app.test_client()
    login_coach(client)
    response, record_id = invitation(client, lifecycle_app)

    assert response.status_code == 200
    assert b"Email was not delivered" in response.data
    assert b"/account/invitation#" in response.data
    with lifecycle_app.app_context():
        assert db.session.get(AccountToken, record_id).delivery_state == state


def test_invitation_requires_confirmed_email_and_coach_authorization(lifecycle_app):
    client = lifecycle_app.test_client()
    assert client.post(f"/athletes/{lifecycle_app.config['IDS']['athlete']}/account/invite").status_code == 302
    login_coach(client)
    response, record_id = invitation(client, lifecycle_app, "wrong@example.test")
    assert response.status_code == 400
    assert record_id is None


def test_activation_once_replay_rejected_and_login_handoff(lifecycle_app):
    coach_client = lifecycle_app.test_client()
    login_coach(coach_client)
    invitation(coach_client, lifecycle_app)
    raw = raw_token_from_message(lifecycle_app)
    path = f"/account/invitation#{raw}"

    athlete_client = lifecycle_app.test_client()
    activated = submit_password(athlete_client, path)
    assert activated.status_code == 302
    assert activated.headers["Location"] == "/athlete/dashboard?welcome=activated"
    landing = athlete_client.get(activated.headers["Location"])
    assert landing.status_code == 200
    assert b"Account activated" in landing.data
    assert athlete_client.get("/coach").status_code == 403
    replay = submit_password(lifecycle_app.test_client(), path)
    assert replay.status_code == 410
    assert b"already been used" in replay.data


def test_invitation_password_mismatch_can_be_corrected_before_single_consumption(lifecycle_app):
    coach_client = lifecycle_app.test_client()
    login_coach(coach_client)
    invitation(coach_client, lifecycle_app)
    raw = raw_token_from_message(lifecycle_app)
    athlete_client = lifecycle_app.test_client()
    page = athlete_client.get("/account/invitation")
    csrf_token = page.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()

    mismatch = athlete_client.post(
        "/account/invitation",
        data={
            "csrf_token": csrf_token,
            "account_token": raw,
            "password": "a sufficiently secure password",
            "password_confirmation": "a different secure password",
        },
    )

    assert mismatch.status_code == 400
    assert mismatch.headers["Cache-Control"] == "no-store"
    assert b"The passwords do not match." in mismatch.data
    assert f'name="account_token" value="{raw}"'.encode() in mismatch.data
    with lifecycle_app.app_context():
        record = AccountToken.query.filter_by(token_digest=digest_token(raw)).one()
        user = db.session.get(User, record.user_id)
        assert record.consumed_at is None
        assert user.active is False
        assert user.password_hash is None

    corrected = athlete_client.post(
        "/account/invitation",
        data={
            "csrf_token": csrf_token,
            "account_token": raw,
            "password": "a sufficiently secure password",
            "password_confirmation": "a sufficiently secure password",
        },
    )
    assert corrected.status_code == 302
    assert corrected.headers["Location"] == "/athlete/dashboard?welcome=activated"
    with lifecycle_app.app_context():
        record = AccountToken.query.filter_by(token_digest=digest_token(raw)).one()
        assert record.consumed_at is not None

    replay = submit_password(lifecycle_app.test_client(), f"/account/invitation#{raw}")
    assert replay.status_code == 410
    assert b"already been used" in replay.data


def test_expired_invitation_is_rejected(lifecycle_app):
    client = lifecycle_app.test_client()
    login_coach(client)
    invitation(client, lifecycle_app)
    raw = raw_token_from_message(lifecycle_app)
    with lifecycle_app.app_context():
        record = AccountToken.query.filter_by(token_digest=digest_token(raw)).one()
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.session.commit()
    assert submit_password(lifecycle_app.test_client(), f"/account/invitation#{raw}").status_code == 410


def test_revoke_and_regenerate_invalidates_previous_link(lifecycle_app):
    client = lifecycle_app.test_client()
    login_coach(client)
    invitation(client, lifecycle_app)
    first = raw_token_from_message(lifecycle_app)
    response, _ = invitation(client, lifecycle_app)
    second = raw_token_from_message(lifecycle_app)
    assert response.status_code == 200 and first != second
    assert submit_password(lifecycle_app.test_client(), f"/account/invitation#{first}").status_code == 410
    assert lifecycle_app.test_client().get("/account/invitation").status_code == 200
    athlete_id = lifecycle_app.config["IDS"]["athlete"]
    client.post(
        f"/athletes/{athlete_id}/account/invitation/revoke",
        data={"csrf_token": csrf_from_session(client)},
    )
    assert submit_password(lifecycle_app.test_client(), f"/account/invitation#{second}").status_code == 410


def test_duplicate_user_linkage_is_rejected(lifecycle_app):
    with lifecycle_app.app_context():
        other = db.session.get(Athlete, lifecycle_app.config["IDS"]["other"])
        owner = User(email="new@example.test", role=UserRole.ATHLETE, athlete_id=other.id, active=False)
        db.session.add(owner)
        db.session.commit()
    client = lifecycle_app.test_client()
    login_coach(client)
    response, _ = invitation(client, lifecycle_app)
    assert response.status_code == 409


def test_password_reset_changes_password_once_and_logs_in(lifecycle_app):
    coach = lifecycle_app.test_client()
    login_coach(coach)
    invitation(coach, lifecycle_app)
    invite_raw = raw_token_from_message(lifecycle_app)
    submit_password(lifecycle_app.test_client(), f"/account/invitation#{invite_raw}")
    athlete_id = lifecycle_app.config["IDS"]["athlete"]
    response = coach.post(
        f"/athletes/{athlete_id}/account/password-reset",
        data={"csrf_token": csrf_from_session(coach)},
    )
    assert response.status_code == 200
    message = lifecycle_app.config["TEST_TRANSPORT"].messages[-1]
    assert message["Subject"] == "Reset your Traditional Strength password"
    reset_raw = message.get_content().split("/account/password_reset#", 1)[1].split()[0]
    athlete = lifecycle_app.test_client()
    reset = submit_password(athlete, f"/account/password_reset#{reset_raw}", "a brand new secure password")
    assert reset.status_code == 302
    assert reset.headers["Location"] == "/athlete/dashboard?welcome=password-updated"
    assert athlete.get("/athlete/dashboard").status_code == 200
    athlete.get("/account/password_reset")
    assert athlete.post(
        f"/athletes/{athlete_id}/account/password-reset",
        data={"csrf_token": csrf_from_session(athlete)},
    ).status_code == 403
    assert submit_password(lifecycle_app.test_client(), f"/account/password_reset#{reset_raw}").status_code == 410
