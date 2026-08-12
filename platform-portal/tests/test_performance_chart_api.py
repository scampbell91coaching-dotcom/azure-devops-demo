from __future__ import annotations

import time
from datetime import UTC, date, datetime

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import WeeklyCheckin
from portal.models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from portal.models.organisation import (
    CoachAthleteOwnership,
    Organisation,
    OrganisationMembership,
    OrganisationRole,
)
from portal.models.user import User, UserRole


@pytest.fixture()
def chart_app():
    app = create_app({
        "TESTING": True,
        "AUTHENTICATION_DISABLED": False,
        "SECRET_KEY": "chart-api-test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        alex = Athlete(first_name="Alex", last_name="Lifter", email="alex-chart@example.com")
        sam = Athlete(first_name="Sam", last_name="Lifter", email="sam-chart@example.com")
        block = TrainingBlock(athlete=alex, name="Meet prep", status="active")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        session = TrainingSession(week=week, name="SBD", position=1)
        slot = ProgrammingLiftSlot(session=session, position=1, lift_family="squat")
        prescription = ExercisePrescription(
            session=session, exercise_name="Competition squat", position=1,
            sets=1, reps="5", rpe=8, slot_role="top_set", lift_slot=slot,
        )
        db.session.add_all([alex, sam, prescription])
        db.session.flush()
        log = TrainingSessionLog(
            athlete_id=alex.id, session_id=session.id, session_name="SBD",
            block_name=block.name, week_name=week.name, status="completed",
            started_at=datetime(2026, 8, 5, 12, tzinfo=UTC),
            completed_at=datetime(2026, 8, 5, 13, tzinfo=UTC),
        )
        db.session.add(log)
        db.session.flush()
        db.session.add_all([
            TrainingSetResult(
                session_log=log, prescription_id=prescription.id,
                exercise_name="Competition squat", exercise_position=1, set_order=1,
                prescribed_reps="5", prescribed_rpe=8, completed=True,
                actual_load_kg=100, actual_reps=5, actual_rpe=8.5,
            ),
            WeeklyCheckin(
                athlete_id=alex.id, week_ending=date(2026, 8, 4),
                average_bodyweight_kg=82.4,
            ),
        ])
        users = [
            User(email="coach-chart@example.com", role=UserRole.COACH, password_hash="unused"),
            User(email=alex.email, role=UserRole.ATHLETE, athlete_id=alex.id, password_hash="unused"),
        ]
        db.session.add_all(users)
        db.session.flush()
        organisation = Organisation(name="Chart Strength", slug="chart-strength")
        db.session.add(organisation)
        db.session.flush()
        membership = OrganisationMembership(
            organisation_id=organisation.id,
            user_id=users[0].id,
            role=OrganisationRole.COACH,
        )
        db.session.add(membership)
        db.session.flush()
        db.session.add_all([
            CoachAthleteOwnership(
                organisation_id=organisation.id,
                coach_membership_id=membership.id,
                athlete_id=athlete.id,
            )
            for athlete in (alex, sam)
        ])
        db.session.commit()
        app.config["CHART_IDS"] = {
            "alex": alex.id, "sam": sam.id, "block": block.id,
            "coach": users[0].id, "alex_user": users[1].id,
        }
    return app


def _sign_in(client, user_id: int) -> None:
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["authenticated_at"] = time.time()


def test_chart_api_returns_chart_ready_filtered_persisted_metrics(chart_app):
    ids = chart_app.config["CHART_IDS"]
    client = chart_app.test_client()
    _sign_in(client, ids["coach"])

    response = client.get(
        f"/api/v1/athletes/{ids['alex']}/performance/charts"
        f"?from=2026-08-01&to=2026-08-10&block_id={ids['block']}"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["filters"]["block_name"] == "Meet prep"
    assert payload["datasets"]["e1rm"] == [{
        "date": "2026-08-05", "lift": "squat", "result_id": 1,
        "top_set": True, "value_kg": 116.67,
    }]
    assert payload["datasets"]["volume"] == [{
        "date": "2026-08-05", "lift": "squat", "value_kg": 500.0,
    }]
    assert payload["datasets"]["rpe"][0]["adherent"] is True
    assert payload["datasets"]["bodyweight"][0]["value_kg"] == 82.4
    assert set(payload["availability"].values()) == {"available"}


def test_chart_api_preserves_coach_only_and_cross_athlete_boundaries(chart_app):
    ids = chart_app.config["CHART_IDS"]
    athlete_client = chart_app.test_client()
    _sign_in(athlete_client, ids["alex_user"])
    assert athlete_client.get(
        f"/api/v1/athletes/{ids['alex']}/performance/charts"
    ).status_code == 403

    coach_client = chart_app.test_client()
    _sign_in(coach_client, ids["coach"])
    assert coach_client.get(
        f"/api/v1/athletes/{ids['sam']}/performance/charts?block_id={ids['block']}"
    ).status_code == 404


@pytest.mark.parametrize("query", ["from=nope", "block_id=0", "from=2026-08-10&to=2026-08-01"])
def test_chart_api_rejects_invalid_filters(chart_app, query):
    client = chart_app.test_client()
    _sign_in(client, chart_app.config["CHART_IDS"]["coach"])
    response = client.get(
        f"/api/v1/athletes/{chart_app.config['CHART_IDS']['alex']}/performance/charts?{query}"
    )
    assert response.status_code == 400


def test_chart_api_marks_missing_history_instead_of_fabricating(chart_app):
    ids = chart_app.config["CHART_IDS"]
    client = chart_app.test_client()
    _sign_in(client, ids["coach"])
    response = client.get(
        f"/api/v1/athletes/{ids['sam']}/performance/charts?from=2026-08-01&to=2026-08-10"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["datasets"] == {"bodyweight": [], "e1rm": [], "rpe": [], "volume": []}
    assert set(payload["availability"].values()) == {"insufficient_data"}
