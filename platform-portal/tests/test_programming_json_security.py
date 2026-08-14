from __future__ import annotations

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import ExercisePrescription, TrainingBlock, TrainingSession, TrainingWeek


@pytest.fixture()
def app():
    instance = create_app(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"}
    )
    with instance.app_context():
        db.create_all()
    return instance


@pytest.fixture()
def programming_ids(app):
    with app.app_context():
        athlete = Athlete(first_name="JSON", last_name="Tester", email="json@test.invalid")
        block = TrainingBlock(athlete=athlete, name="JSON block")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        session = TrainingSession(week=week, name="Day 1", position=1)
        item = ExercisePrescription(session=session, exercise_name="Squat", position=1, sets=3, reps="5")
        db.session.add_all([athlete, block, week, session, item])
        db.session.commit()
        return session.id, item.id


@pytest.mark.parametrize(
    ("body", "content_type"),
    [
        (b"{broken", "application/json"),
        (b"[]", "application/json"),
        (b'"text"', "application/json"),
        (b"{}", "text/plain"),
    ],
)
def test_malformed_or_non_object_programming_json_returns_controlled_error(
    app, programming_ids, body, content_type
):
    session_id, _ = programming_ids
    response = app.test_client().post(
        f"/programming/api/sessions/{session_id}/prescriptions",
        data=body,
        content_type=content_type,
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"exercise_name": "Squat", "sets": "three"},
        {"exercise_name": "Squat", "sets": 10_000},
        {"exercise_name": "Squat", "rpe": float("inf")},
        {"exercise_name": "x" * 161},
        {"exercise_name": None},
        {"exercise_name": "Squat", "unexpected": True},
    ],
)
def test_hostile_programming_values_are_rejected(app, programming_ids, payload):
    session_id, _ = programming_ids
    response = app.test_client().post(
        f"/programming/api/sessions/{session_id}/prescriptions", json=payload
    )
    assert response.status_code == 400


def test_oversized_programming_json_is_rejected(app, programming_ids):
    session_id, _ = programming_ids
    response = app.test_client().post(
        f"/programming/api/sessions/{session_id}/prescriptions",
        json={"exercise_name": "Squat", "notes": "x" * (64 * 1024)},
    )
    assert response.status_code == 413


def test_reorder_rejects_duplicate_and_non_integer_ids(app, programming_ids):
    session_id, prescription_id = programming_ids
    client = app.test_client()
    for ids in ([prescription_id, prescription_id], [str(prescription_id)]):
        response = client.post(
            f"/programming/api/sessions/{session_id}/reorder",
            json={"prescription_ids": ids},
        )
        assert response.status_code == 400
