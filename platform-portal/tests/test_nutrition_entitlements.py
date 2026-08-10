from datetime import UTC, date, datetime

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings
from portal.models.client_service import ClientServiceChange
from portal.models.nutrition_checkin import NutritionCheckIn
from portal.services.coach_dashboard import CoachDashboardService
from portal.services.nutrition_entitlements import nutrition_coaching_enabled


def _app():
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


def _nutrition_record(athlete):
    return NutritionCheckIn(
        athlete=athlete,
        checkin_date=date(2026, 8, 1),
        submitted_at=datetime(2026, 8, 1, tzinfo=UTC),
        nutrition_adherence=8,
        hunger=5,
        energy=7,
        sleep_quality=7,
        stress=4,
        digestion=8,
        training_performance=7,
    )


def test_explicit_disable_blocks_active_routes_but_preserves_coach_history():
    app = _app()
    with app.app_context():
        athlete = Athlete(first_name="No", last_name="Nutrition", email="off@test")
        db.session.add_all([
            athlete,
            AthleteCheckinSettings(
                athlete=athlete,
                training_enabled=True,
                nutrition_enabled=False,
                workflow_active=True,
            ),
            ClientServiceChange(
                athlete=athlete,
                service="nutrition",
                value="no",
                effective_at=datetime(2026, 8, 10),
            ),
            _nutrition_record(athlete),
        ])
        db.session.commit()
        athlete_id = athlete.id
        assert nutrition_coaching_enabled(athlete) is False

        dashboard = CoachDashboardService().build(today=date(2026, 8, 3))
        assert not any(item.url_kind == "nutrition" for item in dashboard.requiring_review)

    client = app.test_client()
    assert client.get(f"/athletes/{athlete_id}/nutrition-checkins/new").status_code == 403
    assert client.post(f"/athletes/{athlete_id}/nutrition-checkins").status_code == 403
    assert client.get(f"/athletes/{athlete_id}/nutrition-import").status_code == 403
    history = client.get(f"/athletes/{athlete_id}")
    assert history.status_code == 200
    assert b"History only" in history.data
    assert b"1 August 2026" in history.data
    assert b"Mark reviewed" not in history.data

    with client.session_transaction() as athlete_session:
        athlete_session["athlete_id"] = athlete_id
    athlete_dashboard = client.get("/athlete/dashboard")
    assert athlete_dashboard.status_code == 200
    assert b">Nutrition</a>" not in athlete_dashboard.data
    assert b"Nutrition &amp; bodyweight" not in athlete_dashboard.data
    assert b"Adherence, calories &amp; protein" not in athlete_dashboard.data


def test_missing_legacy_settings_remains_enabled():
    app = _app()
    with app.app_context():
        athlete = Athlete(first_name="Legacy", last_name="Client", email="legacy@test")
        db.session.add(athlete)
        db.session.commit()
        athlete_id = athlete.id
        assert nutrition_coaching_enabled(athlete) is True

    assert app.test_client().get(
        f"/athletes/{athlete_id}/nutrition-checkins/new"
    ).status_code == 200
