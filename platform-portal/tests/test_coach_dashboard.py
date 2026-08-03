from datetime import UTC, date, datetime

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings, WeeklyCheckin
from portal.models.nutrition_checkin import NutritionCheckIn
from portal.models.programming import TrainingBlock, TrainingWeek
from portal.services.coach_dashboard import CoachDashboardService


def _app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def test_service_aggregates_review_due_flags_programming_and_nutrition():
    app = _app()
    today = date(2026, 8, 3)
    submitted_at = datetime(2026, 8, 2, 18, tzinfo=UTC)

    with app.app_context():
        flagged = Athlete(first_name="Alex", last_name="Flagged", email="a@test")
        unprogrammed = Athlete(
            first_name="Bea", last_name="Pending", email="b@test"
        )
        inactive = Athlete(
            first_name="Cal", last_name="Inactive", email="c@test", status="inactive"
        )
        block = TrainingBlock(athlete=flagged, name="Prep", status="active")
        db.session.add_all(
            [
                flagged,
                unprogrammed,
                inactive,
                block,
                TrainingWeek(block=block, name="Week 1", position=1),
                AthleteCheckinSettings(
                    athlete=unprogrammed,
                    checkin_day=today.weekday(),
                    workflow_active=True,
                    training_enabled=True,
                ),
                WeeklyCheckin(
                    athlete=flagged,
                    week_ending=date(2026, 8, 2),
                    submitted_at=submitted_at,
                    training_included=True,
                    nutrition_included=True,
                    fatigue=8,
                    pain_present=True,
                    average_bodyweight_kg=92.4,
                    calories_average=3000,
                    protein_average_g=190,
                    status="submitted",
                ),
                NutritionCheckIn(
                    athlete=unprogrammed,
                    submitted_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
                    bodyweight_kg=70.5,
                    average_calories=2200,
                    average_protein_g=140,
                    nutrition_adherence=8,
                    hunger=5,
                    energy=7,
                    sleep_quality=7,
                    stress=4,
                    digestion=8,
                    training_performance=7,
                    reviewed=False,
                ),
            ]
        )
        db.session.commit()

        dashboard = CoachDashboardService().build(today=today)

        assert [item.athlete.full_name for item in dashboard.requiring_review] == [
            "Alex Flagged",
            "Bea Pending",
        ]
        assert [item.athlete.full_name for item in dashboard.pending_checkins] == [
            "Bea Pending"
        ]
        assert dashboard.health_flags[0].flags == (
            "High fatigue",
            "Pain reported",
        )
        assert [item.full_name for item in dashboard.without_programme] == [
            "Bea Pending"
        ]
        assert dashboard.programmes_ending_soon == ()
        assert dashboard.programme_timing_available is False
        assert dashboard.nutrition[0].bodyweight_kg == 92.4
        assert dashboard.nutrition[1].calories == 2200


def test_service_uses_only_latest_weekly_checkin_for_health_flags():
    app = _app()
    with app.app_context():
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@test")
        db.session.add_all(
            [
                athlete,
                WeeklyCheckin(
                    athlete=athlete,
                    week_ending=date(2026, 7, 26),
                    submitted_at=datetime(2026, 7, 26, tzinfo=UTC),
                    fatigue=9,
                ),
                WeeklyCheckin(
                    athlete=athlete,
                    week_ending=date(2026, 8, 2),
                    submitted_at=datetime(2026, 8, 2, tzinfo=UTC),
                    fatigue=5,
                ),
            ]
        )
        db.session.commit()

        assert CoachDashboardService().build(today=date(2026, 8, 3)).health_flags == ()


def test_dashboard_route_renders_sections_links_and_unavailable_timing():
    app = _app()
    with app.app_context():
        athlete = Athlete(
            first_name="Alex",
            last_name="Lifter",
            email="alex@test",
            bodyweight_kg=93.5,
        )
        checkin = WeeklyCheckin(
            athlete=athlete,
            week_ending=datetime.now(UTC).date(),
            fatigue=8,
            status="submitted",
        )
        db.session.add_all([athlete, checkin])
        db.session.commit()
        athlete_id = athlete.id
        checkin_id = checkin.id

    response = app.test_client().get("/coach")
    page = response.data.decode()

    assert response.status_code == 200
    for heading in (
        "Athletes requiring review",
        "Pending check-ins",
        "Recent check-ins",
        "Pain and fatigue flags",
        "Programmes ending soon",
        "Bodyweight and nutrition",
        "No current programme",
    ):
        assert heading in page
    assert "Programme timing unavailable" in page
    assert "93.5 kg" in page
    assert f'/athletes/{athlete_id}' in page
    assert f'/athletes/{athlete_id}/programming' in page
    assert f'/check-ins/{checkin_id}' in page


def test_dashboard_renders_clear_empty_states():
    response = _app().test_client().get("/coach")

    assert response.status_code == 200
    assert b"Review queue clear" in response.data
    assert b"Nothing due today" in response.data
    assert b"No recent check-ins" in response.data
    assert b"No bodyweight or nutrition data" in response.data
