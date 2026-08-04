from datetime import UTC, date, datetime

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings, WeeklyCheckin
from portal.services.checkins import due_message


def _app():
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def _athlete(app):
    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@example.com",
        )
        db.session.add(athlete)
        db.session.commit()
        return athlete.id


def _login(client, athlete_id):
    with client.session_transaction() as session:
        session["athlete_id"] = athlete_id


def test_settings_model_reports_due_only_for_active_enabled_workflow():
    app = _app()

    with app.app_context():
        athlete_id = _athlete(app)
        settings = AthleteCheckinSettings(
            athlete_id=athlete_id,
            training_enabled=True,
            nutrition_enabled=False,
            workflow_active=True,
            checkin_day=0,
        )
        db.session.add(settings)
        db.session.commit()

        monday = date(2026, 8, 3)
        assert settings.has_enabled_modules is True
        assert settings.is_due_on(monday) is True
        assert settings.is_due_on(date(2026, 8, 4)) is False

        settings.workflow_active = False
        assert settings.is_due_on(monday) is False
        settings.workflow_active = True
        settings.training_enabled = False
        assert settings.has_enabled_modules is False
        assert settings.is_due_on(monday) is False


def test_settings_model_is_not_due_after_submission_for_that_week():
    app = _app()

    with app.app_context():
        athlete_id = _athlete(app)
        settings = AthleteCheckinSettings(
            athlete_id=athlete_id,
            training_enabled=False,
            nutrition_enabled=True,
            workflow_active=True,
            checkin_day=0,
        )
        db.session.add_all(
            [
                settings,
                WeeklyCheckin(
                    athlete_id=athlete_id,
                    week_ending=date(2026, 8, 9),
                    nutrition_included=True,
                ),
            ]
        )
        db.session.commit()

        assert settings.is_due_on(date(2026, 8, 3)) is False


def test_due_message_distinguishes_due_overdue_and_submitted():
    app = _app()
    with app.app_context():
        athlete_id = _athlete(app)
        settings = AthleteCheckinSettings(
            athlete_id=athlete_id,
            training_enabled=True,
            workflow_active=True,
            checkin_day=0,
        )
        db.session.add(settings)
        db.session.commit()

        assert due_message(settings, date(2026, 8, 3)) == (
            "Your weekly check-in is due today."
        )
        assert "overdue from Monday 03 August" in due_message(
            settings,
            date(2026, 8, 5),
        )
        db.session.add(
            WeeklyCheckin(
                athlete_id=athlete_id,
                week_ending=date(2026, 8, 9),
            )
        )
        db.session.commit()
        assert due_message(settings, date(2026, 8, 5)) is None


def test_settings_route_updates_modules_workflow_and_weekday():
    app = _app()
    athlete_id = _athlete(app)
    client = app.test_client()

    get_response = client.get(f"/athletes/{athlete_id}/check-in-settings")
    assert get_response.status_code == 200
    assert b"Weekly check-in workflow active" in get_response.data

    response = client.post(
        f"/athletes/{athlete_id}/check-in-settings",
        data={
            "training_enabled": "1",
            "nutrition_enabled": "1",
            "workflow_active": "1",
            "checkin_day": "4",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        settings = AthleteCheckinSettings.query.one()
        assert settings.training_enabled is True
        assert settings.nutrition_enabled is True
        assert settings.workflow_active is True
        assert settings.checkin_day == 4


def test_settings_route_deactivates_workflow_and_rejects_invalid_weekday():
    app = _app()
    athlete_id = _athlete(app)

    response = app.test_client().post(
        f"/athletes/{athlete_id}/check-in-settings",
        data={"checkin_day": "9"},
    )

    assert response.status_code == 302
    with app.app_context():
        settings = AthleteCheckinSettings.query.one()
        assert settings.training_enabled is False
        assert settings.nutrition_enabled is False
        assert settings.workflow_active is False
        assert settings.checkin_day == 0
        assert settings.is_due_on(date(2026, 8, 3)) is False


def test_training_only_form_hides_nutrition_fields():
    app = _app()
    athlete_id = _athlete(app)
    client = app.test_client()
    client.post(
        f"/athletes/{athlete_id}/check-in-settings",
        data={"training_enabled": "1", "workflow_active": "1", "checkin_day": "0"},
    )
    _login(client, athlete_id)

    response = client.get(f"/athletes/{athlete_id}/check-ins/new")

    assert response.status_code == 200
    assert b"Training adherence %" in response.data
    assert b"Average bodyweight" not in response.data


def test_nutrition_only_form_hides_training_fields():
    app = _app()
    athlete_id = _athlete(app)
    client = app.test_client()
    client.post(
        f"/athletes/{athlete_id}/check-in-settings",
        data={"nutrition_enabled": "1", "workflow_active": "1", "checkin_day": "0"},
    )
    _login(client, athlete_id)

    response = client.get(f"/athletes/{athlete_id}/check-ins/new")

    assert response.status_code == 200
    assert b"Average bodyweight" in response.data
    assert b"Training adherence %" not in response.data


def test_dynamic_checkin_submission_uses_enabled_modules_only():
    app = _app()
    athlete_id = _athlete(app)

    with app.app_context():
        db.session.add(
            AthleteCheckinSettings(
                athlete_id=athlete_id,
                training_enabled=True,
                nutrition_enabled=False,
                workflow_active=True,
            )
        )
        db.session.commit()

    client = app.test_client()
    _login(client, athlete_id)
    response = client.post(
        f"/athletes/{athlete_id}/check-ins",
        data={
            "week_ending": "2026-08-02",
            "training_adherence": "90",
            "fatigue": "7",
            "recovery": "6",
            "motivation": "8",
            "sleep_quality": "7",
            "stress": "4",
            "calories_average": "3000",
        },
    )

    assert response.status_code == 302
    with app.app_context():
        item = WeeklyCheckin.query.one()
        assert item.training_included is True
        assert item.nutrition_included is False
        assert item.training_adherence == 90
        assert item.calories_average is None


def test_submission_validation_preserves_values_and_does_not_write():
    app = _app()
    athlete_id = _athlete(app)
    client = app.test_client()
    client.post(
        f"/athletes/{athlete_id}/check-in-settings",
        data={"training_enabled": "1", "workflow_active": "1"},
    )
    _login(client, athlete_id)

    response = client.post(
        f"/athletes/{athlete_id}/check-ins",
        data={
            "week_ending": "not-a-date",
            "fatigue": "11",
            "recovery": "steady",
            "general_notes": "Keep this answer",
        },
    )

    assert response.status_code == 400
    assert b"Choose a valid week-ending date" in response.data
    assert b"Fatigue must be between 1 and 10" in response.data
    assert b"Readiness must be a number" in response.data
    assert b"Keep this answer" in response.data
    with app.app_context():
        assert WeeklyCheckin.query.count() == 0


def test_duplicate_week_submission_has_useful_error():
    app = _app()
    athlete_id = _athlete(app)
    with app.app_context():
        db.session.add_all(
            [
                AthleteCheckinSettings(athlete_id=athlete_id),
                WeeklyCheckin(
                    athlete_id=athlete_id,
                    week_ending=date(2026, 8, 2),
                    training_included=True,
                ),
            ]
        )
        db.session.commit()
    client = app.test_client()
    _login(client, athlete_id)

    response = client.post(
        f"/athletes/{athlete_id}/check-ins",
        data={"week_ending": "2026-08-02"},
    )

    assert response.status_code == 400
    assert b"already been submitted for this week" in response.data


def test_athlete_history_receipt_and_coach_response_rendering():
    app = _app()
    athlete_id = _athlete(app)
    with app.app_context():
        item = WeeklyCheckin(
            athlete_id=athlete_id,
            week_ending=date(2026, 8, 2),
            training_included=True,
            recovery=7,
            fatigue=5,
            pain_present=True,
            status="reviewed",
            coach_notes="Keep building steadily.",
        )
        db.session.add(item)
        db.session.commit()
        checkin_id = item.id
    client = app.test_client()
    _login(client, athlete_id)

    history = client.get("/athlete/check-ins")
    receipt = client.get(f"/athlete/check-ins/{checkin_id}")

    assert history.status_code == 200
    assert b"Coach reviewed" in history.data
    assert receipt.status_code == 200
    assert b"Check-in received" in receipt.data
    assert b"Keep building steadily." in receipt.data
    assert b"Readiness" in receipt.data


def test_empty_histories_explain_what_appears_next():
    app = _app()
    athlete_id = _athlete(app)
    client = app.test_client()
    _login(client, athlete_id)

    athlete_history = client.get("/athlete/check-ins")
    coach_index = client.get("/check-ins")

    assert b"No weekly check-ins yet" in athlete_history.data
    assert b"receipt and coach response will appear here" in athlete_history.data
    assert b"No weekly check-ins yet" in coach_index.data
    assert b"appear here for review" in coach_index.data


def test_athlete_routes_require_session_and_isolate_other_athletes():
    app = _app()
    first_id = _athlete(app)
    with app.app_context():
        other = Athlete(
            first_name="Other",
            last_name="Athlete",
            email="other@example.com",
        )
        db.session.add(other)
        db.session.flush()
        item = WeeklyCheckin(
            athlete_id=other.id,
            week_ending=date(2026, 8, 2),
        )
        db.session.add(item)
        db.session.commit()
        other_id = other.id
        other_checkin_id = item.id
    client = app.test_client()

    assert client.get("/athlete/check-ins").status_code == 401
    _login(client, first_id)
    assert client.get(f"/athletes/{other_id}/check-ins/new").status_code == 403
    assert client.get(f"/athlete/check-ins/{other_checkin_id}").status_code == 404


def test_coach_can_access_every_checkin_and_review_requires_response():
    app = _app()
    athlete_id = _athlete(app)
    with app.app_context():
        item = WeeklyCheckin(
            athlete_id=athlete_id,
            week_ending=date(2026, 8, 2),
            status="submitted",
        )
        db.session.add(item)
        db.session.commit()
        checkin_id = item.id
    client = app.test_client()

    assert client.get("/check-ins").status_code == 200
    assert client.get(f"/check-ins/{checkin_id}").status_code == 200
    response = client.post(f"/check-ins/{checkin_id}/review", data={})
    assert response.status_code == 400
    assert b"Add a response before marking this reviewed" in response.data
    with app.app_context():
        assert db.session.get(WeeklyCheckin, checkin_id).status == "submitted"


def test_dashboard_includes_settings_link_and_due_status():
    app = _app()
    athlete_id = _athlete(app)
    client = app.test_client()
    client.post(
        f"/athletes/{athlete_id}/check-in-settings",
        data={
            "training_enabled": "1",
            "workflow_active": "1",
            "checkin_day": str(datetime.now(UTC).date().weekday()),
        },
    )

    response = client.get(f"/athletes/{athlete_id}")

    assert response.status_code == 200
    assert b"Check-in settings" in response.data
    assert b"Weekly check-in due" in response.data


def test_checkin_index_detail_and_review_routes():
    app = _app()
    athlete_id = _athlete(app)

    with app.app_context():
        item = WeeklyCheckin(
            athlete_id=athlete_id,
            week_ending=date(2026, 8, 2),
            training_included=True,
            status="submitted",
        )
        db.session.add(item)
        db.session.commit()
        checkin_id = item.id

    client = app.test_client()
    index_response = client.get("/check-ins")
    detail_response = client.get(f"/check-ins/{checkin_id}")
    review_response = client.post(
        f"/check-ins/{checkin_id}/review",
        data={"coach_notes": "Reduce volume next week."},
    )

    assert index_response.status_code == 200
    assert b"Alex Lifter" in index_response.data
    assert detail_response.status_code == 200
    assert review_response.status_code == 302
    with app.app_context():
        item = db.session.get(WeeklyCheckin, checkin_id)
        assert item.status == "reviewed"
        assert item.coach_notes == "Reduce volume next week."
        assert item.coach_reviewed_at is not None
