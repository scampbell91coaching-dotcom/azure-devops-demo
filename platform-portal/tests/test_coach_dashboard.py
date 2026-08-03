from datetime import UTC, date, datetime

from sqlalchemy import event

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


def test_service_uses_latest_week_ending_for_health_flags():
    app = _app()
    with app.app_context():
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@test")
        db.session.add_all(
            [
                athlete,
                WeeklyCheckin(
                    athlete=athlete,
                    week_ending=date(2026, 8, 2),
                    submitted_at=datetime(2026, 8, 1, tzinfo=UTC),
                    fatigue=5,
                ),
                WeeklyCheckin(
                    athlete=athlete,
                    week_ending=date(2026, 7, 26),
                    submitted_at=datetime(2026, 8, 2, tzinfo=UTC),
                    fatigue=9,
                ),
            ]
        )
        db.session.commit()

        assert CoachDashboardService().build(today=date(2026, 8, 3)).health_flags == ()


def test_service_orders_review_queue_and_pending_athletes_deterministically():
    app = _app()
    today = date(2026, 8, 3)
    submitted_at = datetime(2026, 8, 2, 18, tzinfo=UTC)
    with app.app_context():
        zed = Athlete(first_name="Zed", last_name="Able", email="zed@test")
        amy = Athlete(first_name="Amy", last_name="Baker", email="amy@test")
        inactive = Athlete(
            first_name="Ian", last_name="Dormant", email="ian@test", status="inactive"
        )
        db.session.add_all(
            [
                zed,
                amy,
                inactive,
                AthleteCheckinSettings(athlete=amy, checkin_day=0),
                AthleteCheckinSettings(athlete=zed, checkin_day=0),
                AthleteCheckinSettings(athlete=inactive, checkin_day=0),
                WeeklyCheckin(
                    athlete=zed,
                    week_ending=date(2026, 7, 26),
                    submitted_at=submitted_at,
                    status="submitted",
                ),
                NutritionCheckIn(
                    athlete=amy,
                    submitted_at=submitted_at,
                    nutrition_adherence=8,
                    hunger=5,
                    energy=7,
                    sleep_quality=7,
                    stress=4,
                    digestion=8,
                    training_performance=7,
                ),
            ]
        )
        db.session.commit()

        dashboard = CoachDashboardService().build(today=today)

        assert [item.athlete.full_name for item in dashboard.requiring_review] == [
            "Zed Able",
            "Amy Baker",
        ]
        assert [item.athlete.full_name for item in dashboard.pending_checkins] == [
            "Zed Able",
            "Amy Baker",
        ]


def test_service_build_uses_a_fixed_number_of_selects_for_pending_checkins():
    app = _app()
    today = date(2026, 8, 3)
    with app.app_context():
        for number in range(12):
            athlete = Athlete(
                first_name=f"Athlete {number}",
                last_name="Lifter",
                email=f"athlete-{number}@test",
            )
            db.session.add(athlete)
            db.session.add(AthleteCheckinSettings(athlete=athlete, checkin_day=0))
        db.session.commit()

        selects = 0

        def count_selects(*args):
            nonlocal selects
            if args[2].lstrip().upper().startswith("SELECT"):
                selects += 1

        event.listen(db.engine, "before_cursor_execute", count_selects)
        try:
            dashboard = CoachDashboardService().build(today=today)
        finally:
            event.remove(db.engine, "before_cursor_execute", count_selects)

        assert len(dashboard.pending_checkins) == 12
        assert selects == 5


def test_recent_checkins_cover_exactly_fourteen_calendar_days():
    app = _app()
    today = date(2026, 8, 3)
    with app.app_context():
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@test")
        db.session.add_all(
            [
                athlete,
                WeeklyCheckin(athlete=athlete, week_ending=date(2026, 7, 21)),
                WeeklyCheckin(athlete=athlete, week_ending=date(2026, 7, 20)),
            ]
        )
        db.session.commit()

        recent = CoachDashboardService().build(today=today).recent_checkins

        assert [item.week_ending for item in recent] == [date(2026, 7, 21)]


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
    assert 'href="/athletes/' in page and '#nutrition-checkins' not in page


def test_dashboard_route_is_registered_once_and_nutrition_link_has_a_target():
    app = _app()
    coach_rules = [rule for rule in app.url_map.iter_rules() if rule.rule == "/coach"]

    assert len(coach_rules) == 1

    with app.app_context():
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@test")
        db.session.add(
            NutritionCheckIn(
                athlete=athlete,
                nutrition_adherence=8,
                hunger=5,
                energy=7,
                sleep_quality=7,
                stress=4,
                digestion=8,
                training_performance=7,
            )
        )
        db.session.commit()
        athlete_id = athlete.id

    dashboard = app.test_client().get("/coach").data.decode()
    athlete_page = app.test_client().get(f"/athletes/{athlete_id}").data.decode()

    assert f'href="/athletes/{athlete_id}#nutrition-checkins"' in dashboard
    assert 'id="nutrition-checkins"' in athlete_page


def test_dashboard_renders_clear_empty_states():
    response = _app().test_client().get("/coach")

    assert response.status_code == 200
    assert b"Review queue clear" in response.data
    assert b"Nothing due today" in response.data
    assert b"No recent check-ins" in response.data
    assert b"No bodyweight or nutrition data" in response.data
