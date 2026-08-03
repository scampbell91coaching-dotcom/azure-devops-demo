from datetime import UTC, date, datetime

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import WeeklyCheckin
from portal.models.nutrition_checkin import NutritionCheckIn
from portal.services.nutrition_dashboard import get_nutrition_dashboard


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


def _nutrition_checkin(athlete: Athlete, **values) -> NutritionCheckIn:
    defaults = {
        "athlete": athlete,
        "submitted_at": datetime(2026, 8, 2, 9, 30, tzinfo=UTC),
        "average_calories": 2600,
        "average_protein_g": 190,
        "bodyweight_kg": 91.4,
        "nutrition_adherence": 8,
        "hunger": 5,
        "energy": 7,
        "sleep_quality": 7,
        "stress": 4,
        "digestion": 8,
        "training_performance": 8,
    }
    defaults.update(values)
    return NutritionCheckIn(**defaults)


def test_dashboard_keeps_each_athletes_nutrition_records_isolated():
    app = create_test_app()
    with app.app_context():
        alex = Athlete(first_name="Alex", last_name="Lifter", email="alex@example.com")
        beth = Athlete(first_name="Beth", last_name="Strong", email="beth@example.com")
        db.session.add_all([alex, beth])
        db.session.flush()
        db.session.add_all(
            [
                _nutrition_checkin(alex),
                _nutrition_checkin(
                    beth,
                    submitted_at=datetime(2026, 8, 3, 8, 0, tzinfo=UTC),
                    average_calories=2100,
                    average_protein_g=145,
                    bodyweight_kg=68.2,
                ),
                WeeklyCheckin(
                    athlete=alex,
                    week_ending=date(2026, 8, 2),
                    nutrition_included=True,
                    calories_average=2550,
                    protein_average_g=185,
                    average_bodyweight_kg=91.1,
                    nutrition_adherence=9,
                    submitted_at=datetime(2026, 8, 2, 12, 0, tzinfo=UTC),
                ),
            ]
        )
        db.session.commit()

        dashboard = get_nutrition_dashboard()
        by_name = {item.athlete.full_name: item for item in dashboard.athletes}

        assert by_name["Alex Lifter"].latest_weekly.calories == 2550
        assert {
            record.bodyweight_kg for record in by_name["Alex Lifter"].recent_bodyweights
        } == {91.1, 91.4}
        assert by_name["Beth Strong"].latest.calories == 2100
        assert by_name["Beth Strong"].latest_weekly is None
        assert [
            record.bodyweight_kg for record in by_name["Beth Strong"].recent_bodyweights
        ] == [68.2]


def test_nutrition_route_renders_missing_data_and_undated_profile_weight_safely():
    app = create_test_app()
    with app.app_context():
        athlete = Athlete(
            first_name="No",
            last_name="Checkins",
            email="empty@example.com",
            bodyweight_kg=82.5,
        )
        db.session.add(athlete)
        db.session.commit()
        athlete_id = athlete.id

    response = app.test_client().get("/nutrition")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No nutrition data yet" in page
    assert "Profile bodyweight: 82.5 kg" in page
    assert "Source: Athlete profile (no record date)" in page
    assert f'href="/athletes/{athlete_id}"' in page
    assert "Last submission:" not in page


def test_nutrition_route_labels_sources_dates_and_latest_submission():
    app = create_test_app()
    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@example.com",
        )
        db.session.add(athlete)
        db.session.flush()
        db.session.add(_nutrition_checkin(athlete))
        db.session.commit()

    response = app.test_client().get("/nutrition")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "2600" in page
    assert "190 g" in page
    assert "Source: Nutrition check-in" in page
    assert "Last submission: 02 Aug 2026 at 09:30" in page
    assert "No dated nutrition-enabled weekly check-in is available." in page
