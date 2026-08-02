from datetime import UTC, date, datetime

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings, WeeklyCheckin


def _app():
    return create_app(
        {
            "TESTING": True,
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

    response = app.test_client().post(
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
