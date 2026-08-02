from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings, WeeklyCheckin


def test_training_and_nutrition_toggles():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )

    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@example.com",
        )
        db.session.add(athlete)
        db.session.commit()
        athlete_id = athlete.id

    client = app.test_client()

    response = client.post(
        f"/athletes/{athlete_id}/check-in-settings",
        data={
            "training_enabled": "1",
            "nutrition_enabled": "1",
            "checkin_day": "0",
        },
    )
    assert response.status_code == 302

    with app.app_context():
        settings = AthleteCheckinSettings.query.one()
        assert settings.training_enabled is True
        assert settings.nutrition_enabled is True


def test_dynamic_checkin_submission():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )

    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@example.com",
        )
        db.session.add(athlete)
        db.session.flush()
        db.session.add(
            AthleteCheckinSettings(
                athlete=athlete,
                training_enabled=True,
                nutrition_enabled=False,
            )
        )
        db.session.commit()
        athlete_id = athlete.id

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
        },
    )

    assert response.status_code == 302

    with app.app_context():
        item = WeeklyCheckin.query.one()
        assert item.training_included is True
        assert item.nutrition_included is False
