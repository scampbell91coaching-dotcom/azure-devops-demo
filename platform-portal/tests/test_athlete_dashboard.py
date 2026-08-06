from datetime import UTC, date, datetime

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings, WeeklyCheckin
from portal.models.nutrition_checkin import NutritionCheckIn
from portal.models.programming import ExercisePrescription, TrainingBlock, TrainingSession, TrainingWeek
from portal.services.athlete_dashboard import get_athlete_dashboard


def _app():
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "athlete-dashboard-test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )


def _athlete(first_name: str, email: str) -> Athlete:
    athlete = Athlete(first_name=first_name, last_name="Lifter", email=email)
    db.session.add(athlete)
    db.session.flush()
    return athlete


def _sign_in(client, athlete_id: int) -> None:
    with client.session_transaction() as athlete_session:
        athlete_session["athlete_id"] = athlete_id


def test_service_returns_current_athlete_data_and_first_session_only():
    app = _app()
    with app.app_context():
        athlete = _athlete("Alex", "alex@example.com")
        other = _athlete("Sam", "sam@example.com")
        block = TrainingBlock(athlete_id=athlete.id, name="Strength 1", status="active")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        session = TrainingSession(
            week=week, name="Competition squat", day_label="Monday", position=1
        )
        db.session.add_all(
            [
                block,
                AthleteCheckinSettings(
                    athlete_id=athlete.id,
                    checkin_day=0,
                    training_enabled=True,
                    workflow_active=True,
                ),
                WeeklyCheckin(
                    athlete_id=athlete.id,
                    week_ending=date(2026, 7, 26),
                    submitted_at=datetime(2026, 7, 27, tzinfo=UTC),
                    coach_notes="Keep the top set smooth.",
                    coach_reviewed_at=datetime(2026, 7, 28, tzinfo=UTC),
                ),
                NutritionCheckIn(
                    athlete_id=athlete.id,
                    bodyweight_kg=92.4,
                    average_calories=2800,
                    average_protein_g=190,
                    nutrition_adherence=8,
                    hunger=5,
                    energy=7,
                    sleep_quality=7,
                    stress=4,
                    digestion=8,
                    training_performance=8,
                ),
                TrainingBlock(
                    athlete_id=other.id, name="Private block", status="active"
                ),
            ]
        )
        db.session.commit()

        result = get_athlete_dashboard(athlete.id, today=date(2026, 8, 3))

        assert result is not None
        assert result.current_block is block
        assert result.next_session is session
        assert result.latest_checkin.athlete_id == athlete.id
        assert result.latest_nutrition.bodyweight_kg == 92.4
        assert result.latest_coach_response.body == "Keep the top set smooth."
        assert result.next_checkin_date == date(2026, 8, 3)


def test_service_has_clear_absent_values_without_inventing_data():
    app = _app()
    with app.app_context():
        athlete = _athlete("Alex", "alex@example.com")
        db.session.commit()

        result = get_athlete_dashboard(athlete.id, today=date(2026, 8, 3))

        assert result is not None
        assert result.current_block is None
        assert result.next_session is None
        assert result.latest_checkin is None
        assert result.next_checkin_date is None
        assert result.latest_nutrition is None
        assert result.latest_bodyweight_kg is None
        assert result.latest_coach_response is None


def test_service_returns_bounded_isolated_recent_checkins_and_trends():
    app = _app()
    with app.app_context():
        athlete = _athlete("Alex", "alex@example.com")
        other = _athlete("Sam", "sam@example.com")
        for offset in range(7):
            db.session.add(
                WeeklyCheckin(
                    athlete_id=athlete.id,
                    week_ending=date(2026, 6, 7 + offset),
                    submitted_at=datetime(2026, 6, 7 + offset, tzinfo=UTC),
                    training_included=True,
                    nutrition_included=True,
                    training_adherence=6 + (offset % 3),
                    recovery=5 + (offset % 2),
                    sleep_quality=7,
                    average_bodyweight_kg=90.0 + offset,
                )
            )
        db.session.add_all(
            [
                NutritionCheckIn(
                    athlete_id=athlete.id,
                    submitted_at=datetime(2026, 7, 1, tzinfo=UTC),
                    bodyweight_kg=98.0,
                    nutrition_adherence=8,
                    hunger=5,
                    energy=7,
                    sleep_quality=7,
                    stress=4,
                    digestion=8,
                    training_performance=9,
                ),
                NutritionCheckIn(
                    athlete_id=other.id,
                    submitted_at=datetime(2026, 7, 2, tzinfo=UTC),
                    bodyweight_kg=150.0,
                    nutrition_adherence=8,
                    hunger=5,
                    energy=7,
                    sleep_quality=7,
                    stress=4,
                    digestion=8,
                    training_performance=2,
                ),
            ]
        )
        db.session.commit()

        result = get_athlete_dashboard(athlete.id, today=date(2026, 7, 6))

        assert result is not None
        assert len(result.recent_checkins) == 4
        assert [item.week_ending.day for item in result.recent_checkins] == [
            13,
            12,
            11,
            10,
        ]
        assert len(result.bodyweight_trend) == 6
        assert result.latest_bodyweight_kg == 98.0
        assert all(point.value != 150.0 for point in result.bodyweight_trend)
        assert [point.value for point in result.performance_trend] == [9]


def test_dashboard_requires_an_authenticated_athlete_session():
    app = _app()
    assert app.test_client().get("/athlete/dashboard").status_code == 401


def test_dashboard_is_strictly_isolated_to_signed_in_athlete():
    app = _app()
    with app.app_context():
        alex = _athlete("Alex", "alex@example.com")
        sam = _athlete("Sam", "sam@example.com")
        db.session.add(
            NutritionCheckIn(
                athlete_id=sam.id,
                nutrition_adherence=9,
                hunger=5,
                energy=8,
                sleep_quality=8,
                stress=3,
                digestion=9,
                training_performance=9,
                coach_response="Sam-only response",
            )
        )
        db.session.commit()
        alex_id = alex.id

    client = app.test_client()
    _sign_in(client, alex_id)
    response = client.get("/athlete/dashboard")

    assert response.status_code == 200
    assert b"Welcome back, Alex" in response.data
    assert b"Sam" not in response.data
    assert b"Sam-only response" not in response.data


def test_dashboard_renders_data_empty_states_links_and_no_coach_controls():
    app = _app()
    with app.app_context():
        athlete = _athlete("Alex", "alex@example.com")
        db.session.add(
            AthleteCheckinSettings(
                athlete_id=athlete.id,
                checkin_day=datetime.now(UTC).date().weekday(),
                training_enabled=True,
                workflow_active=True,
            )
        )
        db.session.commit()
        athlete_id = athlete.id

    client = app.test_client()
    _sign_in(client, athlete_id)
    response = client.get("/athlete/dashboard")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No current programme" in page
    assert "No check-ins yet" in page
    assert "No nutrition update yet" in page
    assert "No coach response yet" in page
    assert "No bodyweight trend yet" in page
    assert "No performance trend yet" in page
    assert "No recent check-ins" in page
    assert f"/athletes/{athlete_id}/check-ins/new" in page
    assert f"/athletes/{athlete_id}/nutrition-checkins/new" in page
    assert "Check-in settings" not in page
    assert "Mark reviewed" not in page
    assert "Generate new block" not in page
    assert "Coach Workspace" not in page


def test_athlete_can_view_only_their_active_programme_and_session():
    app = _app()
    with app.app_context():
        athlete = _athlete("Alex", "alex@example.com")
        other = _athlete("Sam", "sam@example.com")
        block = TrainingBlock(athlete=athlete, name="Meet prep", status="active")
        week = TrainingWeek(block=block, name="Week 1", position=1)
        training_session = TrainingSession(week=week, name="Squat day", position=1)
        training_session.prescriptions.append(
            ExercisePrescription(
                exercise_name="Competition squat", sets=3, reps="5", rpe=7
            )
        )
        private_block = TrainingBlock(athlete=other, name="Private", status="active")
        private_week = TrainingWeek(block=private_block, name="Week 1", position=1)
        private_session = TrainingSession(week=private_week, name="Private session", position=1)
        db.session.add_all([block, private_block])
        db.session.commit()
        athlete_id = athlete.id
        session_id = training_session.id
        private_session_id = private_session.id

    client = app.test_client()
    _sign_in(client, athlete_id)
    programme = client.get("/athlete/programme")
    session_response = client.get(f"/athlete/programme/sessions/{session_id}")

    assert programme.status_code == 200
    assert b"Meet prep" in programme.data
    assert b"Private" not in programme.data
    assert session_response.status_code == 200
    assert b"Competition squat" in session_response.data
    assert (
        client.get(f"/athlete/programme/sessions/{private_session_id}").status_code
        == 404
    )


def test_dashboard_renders_compliance_recovery_trends_and_coach_notes():
    app = _app()
    with app.app_context():
        athlete = _athlete("Alex", "alex@example.com")
        db.session.add_all(
            [
                WeeklyCheckin(
                    athlete_id=athlete.id,
                    week_ending=date(2026, 8, 2),
                    submitted_at=datetime(2026, 8, 2, tzinfo=UTC),
                    training_included=True,
                    training_adherence=8,
                    recovery=6,
                    sleep_quality=7,
                    average_bodyweight_kg=92.1,
                    coach_notes="Keep building steadily.",
                    coach_reviewed_at=datetime(2026, 8, 3, tzinfo=UTC),
                ),
                NutritionCheckIn(
                    athlete_id=athlete.id,
                    submitted_at=datetime(2026, 8, 3, tzinfo=UTC),
                    bodyweight_kg=92.4,
                    nutrition_adherence=8,
                    hunger=5,
                    energy=7,
                    sleep_quality=7,
                    stress=4,
                    digestion=8,
                    training_performance=9,
                ),
            ]
        )
        db.session.commit()
        athlete_id = athlete.id

    client = app.test_client()
    _sign_in(client, athlete_id)
    page = client.get("/athlete/dashboard").get_data(as_text=True)

    assert "Training compliance" in page
    assert "8/10" in page
    assert "Recovery" in page
    assert "6/10" in page
    assert "92.4 kg" in page
    assert "9/10" in page
    assert "Keep building steadily." in page
