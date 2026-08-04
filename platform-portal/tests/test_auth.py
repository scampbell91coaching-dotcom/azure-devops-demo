from __future__ import annotations

import time

import pytest
from portal import TESTING_SECRET_KEY, create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.user import User, UserRole


@pytest.fixture
def secured_app():
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": False,
            "SECRET_KEY": "security-test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        first = Athlete(first_name="Ada", last_name="One", email="ada@example.test")
        second = Athlete(first_name="Bea", last_name="Two", email="bea@example.test")
        db.session.add_all([first, second])
        db.session.flush()
        coach = User(email="coach@example.test", role=UserRole.COACH)
        coach.set_password("correct horse battery staple")
        athlete = User(email=first.email, role=UserRole.ATHLETE, athlete_id=first.id)
        athlete.set_password("athlete secure password")
        db.session.add_all([coach, athlete])
        db.session.commit()
        ids = {
            "coach": coach.id,
            "athlete": athlete.id,
            "first": first.id,
            "second": second.id,
        }
    app.config["TEST_IDS"] = ids
    return app


def _csrf(client) -> str:
    response = client.get("/login")
    marker = b'name="csrf_token" value="'
    return response.data.split(marker, 1)[1].split(b'"', 1)[0].decode()


def _login(client, email: str, password: str):
    return client.post(
        "/login",
        data={"email": email, "password": password, "csrf_token": _csrf(client)},
    )


def test_production_startup_requires_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SECRET_KEY must be set"):
        create_app()


def test_testing_startup_uses_safe_test_defaults(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)

    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

    assert app.config["SECRET_KEY"] == TESTING_SECRET_KEY
    assert app.config["AUTHENTICATION_DISABLED"] is True


def test_authentication_remains_enabled_in_production(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "configured-production-secret")

    app = create_app()

    assert app.testing is False
    assert app.config["AUTHENTICATION_DISABLED"] is False


def test_authentication_cannot_be_disabled_outside_testing():
    with pytest.raises(RuntimeError, match="only permitted while testing"):
        create_app(
            {
                "SECRET_KEY": "configured-production-secret",
                "AUTHENTICATION_DISABLED": True,
            }
        )


def test_private_routes_redirect_but_public_routes_remain_public(secured_app):
    client = secured_app.test_client()
    assert client.get("/coach").status_code == 302
    assert client.get("/health").status_code == 200
    assert client.get("/guides/shoulder-pain").status_code == 200


def test_login_is_generic_and_password_is_scrypt_hashed(secured_app):
    client = secured_app.test_client()
    unknown = _login(client, "missing@example.test", "wrong password")
    wrong = _login(client, "coach@example.test", "wrong password")
    assert unknown.status_code == wrong.status_code == 401
    assert b"Invalid email or password." in unknown.data
    assert b"Invalid email or password." in wrong.data
    with secured_app.app_context():
        user = db.session.get(User, secured_app.config["TEST_IDS"]["coach"])
        assert user.password_hash.startswith("scrypt:")
        assert "correct horse" not in user.password_hash


@pytest.mark.parametrize(
    "target",
    [
        "/athletes?view=active#top",
        "/athlete/dashboard",
    ],
)
def test_login_allows_strict_local_redirects(secured_app, target):
    client = secured_app.test_client()
    response = client.post(
        "/login",
        data={
            "email": "coach@example.test",
            "password": "correct horse battery staple",
            "csrf_token": _csrf(client),
            "next": target,
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == target


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/",
        "//evil.example/",
        "/\\evil.example/",
        "/%5cevil.example/",
        "/%2f%2fevil.example/",
        "/%252f%252fevil.example/",
        "/%0d%0aLocation:%20https://evil.example/",
        "/line\nbreak",
        "/\u0085break",
        "/%zz",
        "/%ff",
        "javascript:alert(1)",
    ],
)
def test_login_rejects_unsafe_redirects(secured_app, target):
    client = secured_app.test_client()
    response = client.post(
        "/login",
        data={
            "email": "coach@example.test",
            "password": "correct horse battery staple",
            "csrf_token": _csrf(client),
            "next": target,
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/coach"


def test_login_rotates_session_state(secured_app):
    client = secured_app.test_client()
    original_csrf = _csrf(client)

    response = client.post(
        "/login",
        data={
            "email": "coach@example.test",
            "password": "correct horse battery staple",
            "csrf_token": original_csrf,
        },
    )

    assert response.status_code == 302
    with client.session_transaction() as auth_session:
        assert auth_session["user_id"] == secured_app.config["TEST_IDS"]["coach"]
        assert original_csrf not in auth_session.values()


def test_production_session_cookie_security_flags():
    app = create_app(
        {
            "SECRET_KEY": "configured-production-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    response = app.test_client().get("/login")

    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Secure" in cookie


def test_roles_and_athlete_isolation(secured_app):
    client = secured_app.test_client()
    response = _login(client, "ada@example.test", "athlete secure password")
    assert response.status_code == 302
    ids = secured_app.config["TEST_IDS"]
    assert client.get("/athlete/dashboard").status_code == 200
    assert client.get("/coach").status_code == 403
    assert client.get(f"/athletes/{ids['second']}/check-ins/new").status_code == 404
    assert client.get(f"/athletes/{ids['first']}/check-ins/new").status_code == 200


def test_csrf_logout_and_expired_sessions(secured_app):
    client = secured_app.test_client()
    response = _login(client, "coach@example.test", "correct horse battery staple")
    assert response.status_code == 302
    assert client.post("/logout").status_code == 400
    assert client.get("/coach").status_code == 200
    with client.session_transaction() as auth_session:
        token = auth_session["csrf_token"]
    assert client.post("/logout", data={"csrf_token": token}).status_code == 302
    assert client.get("/coach").status_code == 302

    response = _login(client, "coach@example.test", "correct horse battery staple")
    assert response.status_code == 302
    with client.session_transaction() as auth_session:
        auth_session["authenticated_at"] = time.time() - 9 * 60 * 60
    assert client.get("/coach").status_code == 302


def test_login_rate_limit_is_bounded_and_configurable(secured_app):
    secured_app.config["LOGIN_RATE_LIMIT_ATTEMPTS"] = 2
    client = secured_app.test_client()
    for _ in range(2):
        assert _login(client, "rate-limit@example.test", "wrong").status_code == 401
    response = _login(client, "rate-limit@example.test", "wrong")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "900"
