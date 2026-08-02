from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.nutrition_checkin import NutritionCheckIn


def create_test_app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )

    with app.app_context():
        db.create_all()

    return app


def test_create_athlete_and_view_dashboard():
    app = create_test_app()
    client = app.test_client()

    response = client.post(
        "/athletes",
        data={
            "first_name": "Alex",
            "last_name": "Lifter",
            "email": "alex@example.com",
            "bodyweight_kg": "93.5",
        },
    )

    assert response.status_code == 302

    with app.app_context():
        athlete = Athlete.query.one()

    dashboard = client.get(f"/athletes/{athlete.id}")

    assert dashboard.status_code == 200
    assert b"Alex Lifter" in dashboard.data
    assert b"93.5 kg" in dashboard.data


def test_create_nutrition_checkin():
    app = create_test_app()

    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@example.com",
        )
        db.session.add(athlete)
        db.session.commit()
        athlete_id = athlete.id

    response = app.test_client().post(
        f"/athletes/{athlete_id}/nutrition-checkins",
        data={
            "bodyweight_kg": "92.8",
            "average_calories": "2800",
            "average_protein_g": "200",
            "average_steps": "8000",
            "nutrition_adherence": "8",
            "hunger": "6",
            "energy": "7",
            "sleep_quality": "7",
            "stress": "5",
            "digestion": "8",
            "training_performance": "8",
            "wins": "Hit every target.",
        },
    )

    assert response.status_code == 302

    with app.app_context():
        checkin = NutritionCheckIn.query.one()
        athlete = db.session.get(Athlete, athlete_id)

        assert checkin.nutrition_adherence == 8
        assert checkin.average_protein_g == 200
        assert athlete.bodyweight_kg == 92.8


def test_invalid_checkin_scores_are_rejected():
    app = create_test_app()

    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@example.com",
        )
        db.session.add(athlete)
        db.session.commit()
        athlete_id = athlete.id

    response = app.test_client().post(
        f"/athletes/{athlete_id}/nutrition-checkins",
        data={
            "nutrition_adherence": "15",
            "hunger": "6",
            "energy": "7",
            "sleep_quality": "7",
            "stress": "5",
            "digestion": "8",
            "training_performance": "8",
        },
    )

    assert response.status_code == 400
