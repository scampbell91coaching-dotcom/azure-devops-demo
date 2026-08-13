from __future__ import annotations

import time
from datetime import date

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.meet_day import Meet, MeetEntry, MeetLift
from portal.models.user import User, UserRole
from tenancy_factories import grant_coach_athlete_access


@pytest.fixture
def secured_coaching_app():
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": False,
            "SECRET_KEY": "coaching-route-security-test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.test"
        )
        other_athlete = Athlete(
            first_name="Sam", last_name="Lifter", email="sam@example.test"
        )
        meet = Meet(name="Security Open", meet_date=date(2026, 8, 8))
        entry = MeetEntry(meet=meet, athlete=athlete, flight=1, platform_order=1)
        lift = MeetLift(
            entry=entry,
            lift="squat",
            kind="attempt",
            sequence=1,
            weight_kg=180,
        )
        db.session.add_all([other_athlete, lift])
        db.session.flush()

        coach = User(
            email="coach@example.test",
            password_hash="unused-in-session-test",
            role=UserRole.COACH,
        )
        athlete_user = User(
            email=athlete.email,
            password_hash="unused-in-session-test",
            role=UserRole.ATHLETE,
            athlete_id=athlete.id,
        )
        db.session.add_all([coach, athlete_user])
        grant_coach_athlete_access(
            coach,
            [athlete, other_athlete],
            name="Coaching Security Strength",
            slug="coaching-security-strength",
        )
        db.session.commit()
        app.config["SECURITY_TEST_IDS"] = {
            "athlete": athlete.id,
            "other_athlete": other_athlete.id,
            "coach_user": coach.id,
            "athlete_user": athlete_user.id,
            "meet": meet.id,
            "entry": entry.id,
            "lift": lift.id,
        }
    return app


def _sign_in(client, user_id: int, csrf_token: str = "valid-csrf-token") -> str:
    with client.session_transaction() as auth_session:
        auth_session["user_id"] = user_id
        auth_session["authenticated_at"] = time.time()
        auth_session["csrf_token"] = csrf_token
    return csrf_token


def _coach_page_paths(ids: dict[str, int]) -> list[str]:
    return [
        "/attempt-selection/",
        "/meet-day",
        f"/meet-day/{ids['meet']}",
    ]


@pytest.mark.parametrize("path_index", range(3))
def test_anonymous_users_cannot_access_new_coach_pages(
    secured_coaching_app, path_index
):
    ids = secured_coaching_app.config["SECURITY_TEST_IDS"]
    response = secured_coaching_app.test_client().get(
        _coach_page_paths(ids)[path_index]
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login?next=")


@pytest.mark.parametrize("path_index", range(3))
def test_athlete_sessions_cannot_access_new_coach_pages(
    secured_coaching_app, path_index
):
    ids = secured_coaching_app.config["SECURITY_TEST_IDS"]
    client = secured_coaching_app.test_client()
    _sign_in(client, ids["athlete_user"])

    assert client.get(_coach_page_paths(ids)[path_index]).status_code == 403


def _state_changing_routes(ids: dict[str, int]) -> list[tuple[str, dict[str, str]]]:
    meet_id = ids["meet"]
    entry_id = ids["entry"]
    lift_id = ids["lift"]
    return [
        (
            "/meet-day",
            {"name": "Autumn Open", "meet_date": "2026-09-01"},
        ),
        (
            f"/meet-day/{meet_id}/entries",
            {
                "athlete_id": str(ids["other_athlete"]),
                "flight": "1",
                "platform_order": "2",
            },
        ),
        (
            f"/meet-day/{meet_id}/entries/{entry_id}",
            {"flight": "2", "platform_order": "3"},
        ),
        (
            f"/meet-day/{meet_id}/entries/{entry_id}/lifts",
            {
                "lift": "squat",
                "kind": "attempt",
                "sequence": "2",
                "weight_kg": "190",
                "outcome": "pending",
            },
        ),
        (
            f"/meet-day/{meet_id}/lifts/{lift_id}",
            {"weight_kg": "182.5", "outcome": "good"},
        ),
        (
            f"/meet-day/{meet_id}/plate-calculator",
            {"target_kg": "180", "bar_kg": "20", "collars_kg": "0"},
        ),
        (
            f"/meet-day/{meet_id}/entries/{entry_id}/warmups",
            {
                "lift": "bench",
                "opener_kg": "100",
                "bar_kg": "20",
                "collars_kg": "0",
                "minimum_increment_kg": "2.5",
            },
        ),
    ]


@pytest.mark.parametrize("token", [None, "invalid-csrf-token"])
@pytest.mark.parametrize("route_index", range(7))
def test_state_changing_coach_routes_reject_missing_or_invalid_csrf(
    secured_coaching_app, route_index, token
):
    ids = secured_coaching_app.config["SECURITY_TEST_IDS"]
    client = secured_coaching_app.test_client()
    _sign_in(client, ids["coach_user"])
    path, data = _state_changing_routes(ids)[route_index]
    if token is not None:
        data["csrf_token"] = token

    response = client.post(path, data=data)

    assert response.status_code == 400
    assert b"Invalid CSRF token" in response.data


@pytest.mark.parametrize("token", [None, "invalid-csrf-token"])
def test_read_only_attempt_calculation_still_obeys_post_csrf_enforcement(
    secured_coaching_app, token
):
    ids = secured_coaching_app.config["SECURITY_TEST_IDS"]
    client = secured_coaching_app.test_client()
    _sign_in(client, ids["coach_user"])
    data = {"lift": "squat", "unit": "kg", "reference_load": "200"}
    if token is not None:
        data["csrf_token"] = token

    response = client.post("/attempt-selection/", data=data)

    assert response.status_code == 400
    assert b"Invalid CSRF token" in response.data


def test_authorized_coach_can_use_every_new_route(secured_coaching_app):
    ids = secured_coaching_app.config["SECURITY_TEST_IDS"]
    client = secured_coaching_app.test_client()
    csrf_token = _sign_in(client, ids["coach_user"])

    for path in _coach_page_paths(ids):
        assert client.get(path).status_code == 200

    recommendation = client.post(
        "/attempt-selection/",
        data={
            "csrf_token": csrf_token,
            "lift": "squat",
            "unit": "kg",
            "reference_load": "200",
            "opener_percent": "90",
            "second_percent": "95",
            "third_percent": "100",
            "rounding_increment": "2.5",
        },
    )
    assert recommendation.status_code == 200
    assert b"Recommended plan" in recommendation.data

    for path, data in _state_changing_routes(ids):
        data["csrf_token"] = csrf_token
        expected = 200 if path.endswith("plate-calculator") else 302
        assert client.post(path, data=data).status_code == expected


def test_authenticated_prescription_form_carries_csrf_and_posts_successfully(
    secured_coaching_app,
):
    ids = secured_coaching_app.config["SECURITY_TEST_IDS"]
    client = secured_coaching_app.test_client()
    csrf_token = _sign_in(client, ids["coach_user"])
    with secured_coaching_app.app_context():
        from portal.models.programming import TrainingBlock, TrainingSession, TrainingWeek

        athlete = db.session.get(Athlete, ids["athlete"])
        block = TrainingBlock(athlete=athlete, name="CSRF regression")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        training_session = TrainingSession(week=week, name="Lower", position=1)
        db.session.add(block)
        db.session.commit()
        session_id = training_session.id

    page = client.get(f"/programming/sessions/{session_id}")
    assert page.status_code == 200
    assert b'data-new-prescription-form' in page.data
    assert f'name="csrf_token" value="{csrf_token}"'.encode() in page.data
    response = client.post(
        f"/programming/sessions/{session_id}/prescriptions",
        data={
            "csrf_token": csrf_token,
            "exercise_name": "Competition Squat",
            "sets": "4",
            "reps": "5",
            "rpe": "7.5",
        },
    )
    assert response.status_code == 302


def test_existing_athlete_authorization_boundaries_remain_intact(
    secured_coaching_app,
):
    ids = secured_coaching_app.config["SECURITY_TEST_IDS"]
    assert (
        secured_coaching_app.test_client().get("/athlete/dashboard").status_code == 302
    )

    client = secured_coaching_app.test_client()
    _sign_in(client, ids["athlete_user"])

    assert (
        client.post(
            "/programming/blocks/999999/activate",
            data={"csrf_token": "unused"},
        ).status_code
        == 403
    )

    assert client.get("/athlete/dashboard").status_code == 200
    assert (
        client.get(
            f"/athletes/{ids['other_athlete']}/nutrition-checkins/new"
        ).status_code
        == 404
    )
