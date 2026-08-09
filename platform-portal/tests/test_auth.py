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


def _csrf_from_session(client) -> str:
    with client.session_transaction() as auth_session:
        return auth_session["csrf_token"]


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


@pytest.mark.parametrize("path", ["/health", "/coach", "/missing"])
def test_security_headers_cover_private_app_response_classes(secured_app, path):
    response = secured_app.test_client().get(path, base_url="https://portal.example")

    assert response.headers["Content-Security-Policy"] == (
        "default-src 'self'; base-uri 'self'; connect-src 'self'; font-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; "
        "media-src 'self'; object-src 'none'; "
        "script-src 'self' https://cdn.jsdelivr.net; style-src 'self'; "
        "upgrade-insecure-requests"
    )
    assert response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == (
        "camera=(), geolocation=(), microphone=()"
    )
    assert response.headers["Cache-Control"] == "no-store"


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


def test_login_template_has_branded_accessible_controls(secured_app):
    response = secured_app.test_client().get("/login")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'alt="Traditional Strength"' in html
    assert 'name="email"' in html and 'autocomplete="username"' in html
    assert 'name="password"' in html and 'autocomplete="current-password"' in html
    assert 'data-password-toggle' in html
    assert 'aria-label="Show password"' in html
    assert "Coach access" in html
    assert "Athlete access" in html


def test_edge_identity_prefills_email_but_still_requires_app_password(secured_app):
    client = secured_app.test_client()
    response = client.get(
        "/login", headers={"X-Auth-Request-Email": "ADA@EXAMPLE.TEST"}
    )
    html = response.get_data(as_text=True)
    assert 'value="ada@example.test"' in html
    assert "Identity check complete" in html

    rejected = client.post(
        "/login",
        headers={"X-Auth-Request-Email": "ada@example.test"},
        data={
            "email": "ada@example.test",
            "password": "wrong password",
            "csrf_token": _csrf_from_session(client),
        },
    )
    assert rejected.status_code == 401


def test_login_preserves_safe_athlete_destination(secured_app):
    client = secured_app.test_client()
    response = client.get("/athlete/programme")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(
        "/login?next=/athlete/programme"
    )
    login_page = client.get(response.headers["Location"])
    assert login_page.status_code == 200
    logged_in = client.post(
        response.headers["Location"],
        data={
            "email": "ada@example.test",
            "password": "athlete secure password",
            "csrf_token": _csrf_from_session(client),
            "next": "/athlete/programme",
        },
    )
    assert logged_in.status_code == 302
    assert logged_in.headers["Location"] == "/athlete/programme"


def test_account_delivery_readiness_command_redacts_credentials(secured_app):
    secured_app.config.update(
        ACCOUNT_PUBLIC_BASE_URL="https://athletes.example.test",
        SMTP_HOST="smtp.example.test",
        SMTP_USERNAME="smtp-user",
        SMTP_PASSWORD="super-secret-value",
    )
    result = secured_app.test_cli_runner().invoke(args=["account-delivery-readiness"])
    assert result.exit_code == 0
    assert "public_base_url: https://athletes.example.test" in result.output
    assert "transport: configured" in result.output
    assert "smtp_auth: configured" in result.output
    assert "super-secret-value" not in result.output


def test_invalid_login_error_is_announced_without_account_disclosure(secured_app):
    response = _login(secured_app.test_client(), "missing@example.test", "wrong")
    html = response.get_data(as_text=True)

    assert 'role="alert"' in html
    assert 'aria-live="assertive"' in html
    assert 'aria-invalid="true"' in html
    assert "Invalid email or password." in html
    assert "missing@example.test" not in html


@pytest.mark.parametrize(
    ("email", "password", "expected"),
    [
        ("coach@example.test", "correct horse battery staple", "/coach"),
        ("ada@example.test", "athlete secure password", "/athlete/dashboard"),
    ],
)
def test_successful_login_uses_role_aware_destination(
    secured_app, email, password, expected
):
    response = _login(secured_app.test_client(), email, password)

    assert response.status_code == 302
    assert response.headers["Location"] == expected


@pytest.mark.parametrize(
    ("email", "password", "expected"),
    [
        ("coach@example.test", "correct horse battery staple", "/coach"),
        ("ada@example.test", "athlete secure password", "/athlete/dashboard"),
    ],
)
def test_legacy_root_next_uses_role_aware_destination(
    secured_app, email, password, expected
):
    client = secured_app.test_client()
    response = client.post(
        "/login",
        data={
            "email": email,
            "password": password,
            "csrf_token": _csrf(client),
            "next": "/",
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"] == expected


@pytest.mark.parametrize(
    ("email", "password", "expected"),
    [
        ("coach@example.test", "correct horse battery staple", "/coach"),
        ("ada@example.test", "athlete secure password", "/athlete/dashboard"),
    ],
)
def test_authenticated_login_visit_uses_role_aware_destination(
    secured_app, email, password, expected
):
    client = secured_app.test_client()
    assert _login(client, email, password).status_code == 302

    response = client.get("/login")

    assert response.status_code == 302
    assert response.headers["Location"] == expected


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
    assert client.get(f"/athletes/{ids['second']}/nutrition-checkins/new").status_code == 404
    assert client.get(f"/athletes/{ids['first']}/nutrition-checkins/new").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/coach",
        "/athletes",
        "/programming",
        "/check-ins",
        "/nutrition",
        "/applications",
        "/meet-day",
    ],
)
def test_athlete_cannot_access_release_critical_coach_surfaces(secured_app, path):
    client = secured_app.test_client()
    assert _login(client, "ada@example.test", "athlete secure password").status_code == 302

    response = client.get(path)

    assert response.status_code == 403
    assert b"Access denied" in response.data


def test_coach_can_create_and_update_nutrition_response(secured_app):
    client = secured_app.test_client()
    assert _login(client, "coach@example.test", "correct horse battery staple").status_code == 302
    athlete_id = secured_app.config["TEST_IDS"]["first"]
    with secured_app.app_context():
        from portal.models.nutrition_checkin import NutritionCheckIn
        item = NutritionCheckIn(
            athlete_id=athlete_id, nutrition_adherence=8, hunger=5, energy=7,
            sleep_quality=7, digestion=8, stress=5, training_performance=7,
        )
        db.session.add(item)
        db.session.commit()
        item_id = item.id
    page = client.get(f"/athletes/{athlete_id}/nutrition-checkins/new")
    csrf = page.data.split(b'name="csrf_token" value="', 1)[1].split(b'"', 1)[0].decode()
    response = client.post(
        f"/athletes/{athlete_id}/nutrition-checkins/{item_id}/review",
        data={"csrf_token": csrf, "coach_response": "Good consistency.", "review_status": "reviewed"},
    )
    assert response.status_code == 302
    with secured_app.app_context():
        item = db.session.get(NutritionCheckIn, item_id)
        assert item.coach_response == "Good consistency."
        assert item.reviewed is True
        assert item.reviewed_at is not None
    client.post(
        f"/athletes/{athlete_id}/nutrition-checkins/{item_id}/review",
        data={"csrf_token": csrf, "coach_response": "Updated feedback.", "review_status": "needs_review"},
    )
    with secured_app.app_context():
        item = db.session.get(NutritionCheckIn, item_id)
        assert item.coach_response == "Updated feedback."
        assert item.reviewed is False


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
    expired = client.get("/coach")
    assert expired.status_code == 302
    assert "reason=session_expired" in expired.headers["Location"]
    notice = client.get(expired.headers["Location"])
    assert b"Your session has ended" in notice.data


def test_access_denied_uses_auth_specific_secure_state(secured_app):
    client = secured_app.test_client()
    assert _login(client, "ada@example.test", "athlete secure password").status_code == 302
    response = client.get("/coach")

    assert response.status_code == 403
    assert b"Access denied" in response.data
    assert b"Your account and session are still secure" in response.data
    assert b'href="/athlete/dashboard"' in response.data

def test_login_rate_limit_is_bounded_and_configurable(secured_app):
    secured_app.config["LOGIN_RATE_LIMIT_ATTEMPTS"] = 2
    client = secured_app.test_client()
    for _ in range(2):
        assert _login(client, "rate-limit@example.test", "wrong").status_code == 401
    response = _login(client, "rate-limit@example.test", "wrong")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "900"
