from datetime import UTC, date, datetime

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import TrainingBlock, TrainingSession, TrainingSessionLog, TrainingWeek
from portal.services.training_schedule import local_today, project_training_schedule


def _schedule_fixture():
    athlete = Athlete(first_name="Alex", last_name="Lifter", email="schedule@example.com")
    block = TrainingBlock(athlete=athlete, name="Beta block", status="active")
    week_1 = TrainingWeek(block=block, name="Foundation", position=1)
    week_2 = TrainingWeek(block=block, name="Build", position=2)
    sessions = [
        TrainingSession(week=week_1, name="Day one", day_label="Monday", position=1),
        TrainingSession(week=week_1, name="Day two", day_label="Thursday", position=2),
        TrainingSession(week=week_2, name="Day three", position=1),
    ]
    db.session.add(block)
    db.session.flush()
    return athlete, block, sessions


def test_missing_dates_use_programme_order_and_do_not_claim_today():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        _, block, sessions = _schedule_fixture()
        schedule = project_training_schedule(block, {}, today=date(2026, 8, 9))
        assert schedule.next_session.session is sessions[0]
        assert schedule.current_week.position == 1
        assert schedule.today_session is None
        assert schedule.has_planned_dates is False
        assert schedule.next_session.timing_label(date(2026, 8, 9)) == "Date not set · programme order"


def test_completed_sessions_are_skipped_and_progress_moves_week():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        athlete, block, sessions = _schedule_fixture()
        logs = {
            item.id: TrainingSessionLog(
                athlete=athlete, session=item, session_name=item.name,
                block_name=block.name, week_name=item.week.name, status="completed",
            )
            for item in sessions[:2]
        }
        schedule = project_training_schedule(block, logs, today=date(2026, 8, 9))
        assert schedule.next_session.session is sessions[2]
        assert schedule.current_week.position == 2


def test_dated_schedule_handles_today_future_and_boundary_dates():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        _, block, sessions = _schedule_fixture()
        dates = {
            sessions[0].id: date(2026, 12, 31),
            sessions[1].id: date(2027, 1, 1),
            sessions[2].id: date(2027, 1, 4),
        }
        schedule = project_training_schedule(block, {}, today=date(2027, 1, 1), planned_dates=dates)
        assert schedule.today_session.session is sessions[1]
        assert schedule.next_session.session is sessions[0]
        assert schedule.next_session.timing_label(date(2027, 1, 1)).startswith("Overdue")
        assert schedule.has_planned_dates is True


def test_completed_dated_session_does_not_hide_future_next_session():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        athlete, block, sessions = _schedule_fixture()
        log = TrainingSessionLog(
            athlete=athlete, session=sessions[0], session_name=sessions[0].name,
            block_name=block.name, week_name=sessions[0].week.name, status="completed",
        )
        schedule = project_training_schedule(
            block, {sessions[0].id: log}, today=date(2026, 8, 9),
            planned_dates={sessions[0].id: date(2026, 8, 9), sessions[1].id: date(2026, 8, 10)},
        )
        assert schedule.today_session is None
        assert schedule.next_session.session is sessions[1]


def test_programme_anchor_derives_week_session_and_end_dates_at_year_boundary():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        _, block, sessions = _schedule_fixture()
        block.start_date = date(2026, 12, 28)
        block.timezone = "Europe/London"
        schedule = project_training_schedule(block, {}, today=date(2027, 1, 4))
        assert [item.planned_on for item in schedule.sessions] == [
            date(2026, 12, 28), date(2026, 12, 29), date(2027, 1, 4)
        ]
        assert block.weeks[1].starts_on == date(2027, 1, 4)
        assert schedule.programme_end == date(2027, 1, 10)
        assert schedule.current_week.position == 1  # earliest unfinished session is deterministic


def test_local_today_uses_explicit_timezone_at_utc_boundary():
    instant = datetime(2027, 1, 1, 0, 30, tzinfo=UTC)
    assert local_today("America/New_York", now=instant) == date(2026, 12, 31)
    assert local_today("Pacific/Auckland", now=instant) == date(2027, 1, 1)
