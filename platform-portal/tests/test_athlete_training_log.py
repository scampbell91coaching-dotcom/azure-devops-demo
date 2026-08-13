from __future__ import annotations

import time

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from portal.models.user import User, UserRole
from portal.services.coach_athlete_performance import get_coach_athlete_performance
from tenancy_factories import grant_coach_athlete_access


@pytest.fixture()
def training_app():
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": False,
            "SECRET_KEY": "training-log-test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        db.create_all()
        alex = Athlete(first_name="Alex", last_name="Lifter", email="alex@example.com")
        sam = Athlete(first_name="Sam", last_name="Lifter", email="sam@example.com")
        block = TrainingBlock(athlete=alex, name="Meet prep", status="active")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        session = TrainingSession(week=week, name="Squat day", position=1)
        squat = ExercisePrescription(
            session=session,
            exercise_name="Competition squat",
            position=1,
            sets=2,
            reps="5",
            load_kg=100,
            rpe=7,
            notes="Stay balanced.",
        )
        db.session.add_all([alex, sam, block, squat])
        db.session.flush()
        users = [
            User(
                email="coach@example.com",
                role=UserRole.COACH,
                password_hash="unused",
            ),
            User(
                email=alex.email,
                role=UserRole.ATHLETE,
                athlete_id=alex.id,
                password_hash="unused",
            ),
            User(
                email=sam.email,
                role=UserRole.ATHLETE,
                athlete_id=sam.id,
                password_hash="unused",
            ),
        ]
        db.session.add_all(users)
        grant_coach_athlete_access(
            users[0], [alex], name="Training Log Strength", slug="training-log-strength"
        )
        db.session.commit()
        app.config["TRAINING_IDS"] = {
            "alex": alex.id,
            "sam": sam.id,
            "session": session.id,
            "prescription": squat.id,
            "coach_user": users[0].id,
            "alex_user": users[1].id,
            "sam_user": users[2].id,
        }
    return app


def _sign_in(client, user_id: int) -> str:
    token = f"csrf-{user_id}"
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["authenticated_at"] = time.time()
        session["csrf_token"] = token
    return token


def _set_data(prescription_id: int, order: int, **values):
    prefix = f"set-{prescription_id}-{order}"
    data = {f"row-{prescription_id}-{order}": "1"}
    data.update({f"{prefix}-{key}": str(value) for key, value in values.items()})
    return data


def test_first_result_starts_session_and_reload_persists(training_app):
    ids = training_app.config["TRAINING_IDS"]
    client = training_app.test_client()
    token = _sign_in(client, ids["alex_user"])
    data = _set_data(
        ids["prescription"], 1, completed=1, load=102.5, reps=5, rpe=7.5, note="Smooth"
    )
    data.update(intent="save", csrf_token=token)

    response = client.post(f"/athlete/programme/sessions/{ids['session']}", data=data)
    page = client.get(f"/athlete/programme/sessions/{ids['session']}")

    assert response.status_code == 302
    assert b"In Progress" in page.data
    assert b'value="102.5"' in page.data
    with training_app.app_context():
        log = TrainingSessionLog.query.one()
        result = TrainingSetResult.query.one()
        assert log.status == "in_progress"
        assert result.completed is True
        assert result.athlete_note == "Smooth"
        assert result.prescribed_load_kg == 100


def test_multiple_sets_skip_extra_and_duplicate_save_are_idempotent(training_app):
    ids = training_app.config["TRAINING_IDS"]
    client = training_app.test_client()
    token = _sign_in(client, ids["alex_user"])
    data = _set_data(ids["prescription"], 1, completed=1, load=100, reps=5, rpe=7)
    data.update(_set_data(ids["prescription"], 2, skipped=1, note="Knee felt off"))
    data.update(_set_data(ids["prescription"], 3, completed=1, load=90, reps=6, rpe=6))
    data.update(intent="save", csrf_token=token)

    assert (
        client.post(
            f"/athlete/programme/sessions/{ids['session']}", data=data
        ).status_code
        == 302
    )
    assert (
        client.post(
            f"/athlete/programme/sessions/{ids['session']}", data=data
        ).status_code
        == 302
    )

    with training_app.app_context():
        results = TrainingSetResult.query.order_by(TrainingSetResult.set_order).all()
        assert len(results) == 3
        assert results[1].skipped is True
        assert results[1].athlete_note == "Knee felt off"
        assert results[2].is_extra is True


def test_finish_requires_every_set_then_locks_completed_history(training_app):
    ids = training_app.config["TRAINING_IDS"]
    client = training_app.test_client()
    token = _sign_in(client, ids["alex_user"])
    incomplete = _set_data(ids["prescription"], 1, completed=1, reps=5)
    incomplete.update(intent="finish", csrf_token=token)
    assert (
        client.post(
            f"/athlete/programme/sessions/{ids['session']}", data=incomplete
        ).status_code
        == 400
    )

    complete = _set_data(ids["prescription"], 1, completed=1, load=100, reps=5, rpe=7)
    complete.update(_set_data(ids["prescription"], 2, skipped=1))
    complete.update(intent="finish", csrf_token=token)
    assert (
        client.post(
            f"/athlete/programme/sessions/{ids['session']}", data=complete
        ).status_code
        == 302
    )

    changed = _set_data(ids["prescription"], 1, completed=1, load=200, reps=5)
    changed.update(intent="save", csrf_token=token)
    assert (
        client.post(
            f"/athlete/programme/sessions/{ids['session']}", data=changed
        ).status_code
        == 400
    )
    with training_app.app_context():
        log = TrainingSessionLog.query.one()
        assert log.status == "completed"
        assert log.completed_at is not None
        assert log.results[0].actual_load_kg == 100


@pytest.mark.parametrize(
    "values",
    [
        {"completed": 1, "reps": 1001},
        {"completed": 1, "reps": 5, "load": -1},
        {"completed": 1, "reps": 5, "rpe": 10.5},
        {"completed": 1, "reps": "five"},
    ],
)
def test_invalid_numeric_data_is_rejected_without_persistence(training_app, values):
    ids = training_app.config["TRAINING_IDS"]
    client = training_app.test_client()
    token = _sign_in(client, ids["alex_user"])
    data = _set_data(ids["prescription"], 1, **values)
    data.update(intent="save", csrf_token=token)
    assert (
        client.post(
            f"/athlete/programme/sessions/{ids['session']}", data=data
        ).status_code
        == 400
    )
    with training_app.app_context():
        assert TrainingSessionLog.query.count() == 0


def test_invalid_ids_ownership_csrf_and_coach_only_review(training_app):
    ids = training_app.config["TRAINING_IDS"]
    path = f"/athlete/programme/sessions/{ids['session']}"
    assert training_app.test_client().post(path, data={}).status_code == 302

    sam_client = training_app.test_client()
    sam_token = _sign_in(sam_client, ids["sam_user"])
    assert sam_client.get(path).status_code == 404
    assert sam_client.post(path, data={"csrf_token": sam_token}).status_code == 404

    alex_client = training_app.test_client()
    alex_token = _sign_in(alex_client, ids["alex_user"])
    assert alex_client.post(path, data={}).status_code == 400
    assert (
        alex_client.post(
            "/athlete/programme/sessions/999999", data={"csrf_token": alex_token}
        ).status_code
        == 404
    )


def test_coach_can_review_actual_vs_prescribed_but_athlete_cannot(training_app):
    ids = training_app.config["TRAINING_IDS"]
    athlete_client = training_app.test_client()
    token = _sign_in(athlete_client, ids["alex_user"])
    data = _set_data(
        ids["prescription"], 1, completed=1, load=105, reps=4, rpe=8, note="Hard rep"
    )
    data.update(_set_data(ids["prescription"], 2, skipped=1))
    data.update(intent="finish", csrf_token=token)
    athlete_client.post(f"/athlete/programme/sessions/{ids['session']}", data=data)
    with training_app.app_context():
        log_id = TrainingSessionLog.query.one().id
    review_path = f"/athletes/{ids['alex']}/training-sessions/{log_id}"
    assert athlete_client.get(review_path).status_code == 403

    coach_client = training_app.test_client()
    _sign_in(coach_client, ids["coach_user"])
    review = coach_client.get(review_path)
    assert review.status_code == 200
    assert b"105.0 kg" in review.data
    assert b"target 100.0 kg" in review.data
    assert b"Hard rep" in review.data
    assert (
        coach_client.get(
            f"/athletes/{ids['sam']}/training-sessions/{log_id}"
        ).status_code
        == 404
    )


def test_prescription_edits_do_not_overwrite_result_snapshot(training_app):
    ids = training_app.config["TRAINING_IDS"]
    client = training_app.test_client()
    token = _sign_in(client, ids["alex_user"])
    data = _set_data(ids["prescription"], 1, completed=1, load=105, reps=5)
    data.update(intent="save", csrf_token=token)
    client.post(f"/athlete/programme/sessions/{ids['session']}", data=data)
    with training_app.app_context():
        prescription = db.session.get(ExercisePrescription, ids["prescription"])
        prescription.load_kg = 120
        db.session.commit()
        assert TrainingSetResult.query.one().prescribed_load_kg == 100


def test_coach_performance_dashboard_uses_results_and_explains_decision(training_app):
    ids = training_app.config["TRAINING_IDS"]
    athlete_client = training_app.test_client()
    token = _sign_in(athlete_client, ids["alex_user"])
    data = _set_data(ids["prescription"], 1, completed=1, load=100, reps=4, rpe=8)
    data.update(_set_data(ids["prescription"], 2, skipped=1))
    data.update(intent="finish", csrf_token=token)
    athlete_client.post(f"/athlete/programme/sessions/{ids['session']}", data=data)

    with training_app.app_context():
        performance = get_coach_athlete_performance(ids["alex"])
        block_id = TrainingBlock.query.filter_by(athlete_id=ids["alex"]).one().id
        assert performance.session_count == 1
        assert performance.completed_reps == 4
        assert performance.missed_reps == 6
        assert performance.volume_kg == 400
        assert performance.rpe_adherence_percent == 0
        assert performance.decision.status == "review"

    coach_client = training_app.test_client()
    _sign_in(coach_client, ids["coach_user"])
    page = coach_client.get(f"/athletes/{ids['alex']}?block={block_id}").get_data(
        as_text=True
    )
    assert "Performance dashboard" in page
    assert "Review prescription before progressing" in page
    assert "400 kg" in page
    assert "0%" in page
    assert "Epley" in page
    assert 'aria-label="Athlete context"' in page
    assert "Open programme" in page
    assert ">Programming</a>" in page
    assert ">Training log</a>" in page
    assert 'href="#client-services">Administration</a>' in page
    assert "How this decision is made" in page
    assert 'aria-label="Primary training metrics"' in page
    assert 'aria-label="Supporting training metrics"' in page
    assert "Supporting context" in page


def test_performance_filter_rejects_another_athletes_block(training_app):
    ids = training_app.config["TRAINING_IDS"]
    with training_app.app_context():
        private = TrainingBlock(
            athlete_id=ids["sam"], name="Sam private", status="active"
        )
        db.session.add(private)
        db.session.commit()
        private_id = private.id

    coach_client = training_app.test_client()
    _sign_in(coach_client, ids["coach_user"])
    response = coach_client.get(f"/athletes/{ids['alex']}?block={private_id}")
    assert response.status_code == 404
    assert b"Sam private" not in response.data
