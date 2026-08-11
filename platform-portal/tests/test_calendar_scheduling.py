from datetime import date

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import AthleteCheckinSettings
from portal.models.programming import TrainingBlock, TrainingSession, TrainingWeek
from portal.services.calendar_scheduling import (
    CheckinState,
    CompetitionDate,
    project_athlete_scheduling,
    project_checkin_timing,
)
from portal.services.holiday_mode import (
    HolidayPeriod,
    ProgrammingIntent,
    Provenance,
    SessionAction,
    SessionContext,
    TrainingAvailability,
)


def _app():
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


def _programme():
    athlete = Athlete(first_name="Alex", last_name="Lifter", email="calendar@example.com")
    block = TrainingBlock(athlete=athlete, name="Competition block", status="active")
    week = TrainingWeek(block=block, name="Peak", position=1)
    sessions = [
        TrainingSession(week=week, name="Squat", position=1),
        TrainingSession(week=week, name="Bench", position=2),
    ]
    db.session.add(block)
    db.session.flush()
    return athlete, block, sessions


def _holiday(athlete_id, holiday_id="trip", starts_on=date(2026, 8, 12), ends_on=date(2026, 8, 14)):
    return HolidayPeriod(
        holiday_id=holiday_id,
        athlete_id=athlete_id,
        starts_on=starts_on,
        ends_on=ends_on,
        availability=TrainingAvailability.NONE,
        programming_intent=ProgrammingIntent.PAUSE,
        provenance=Provenance.ATHLETE_SUBMITTED,
    )


def test_projection_joins_planned_sessions_competition_and_travel_without_moving_dates():
    app = _app()
    with app.app_context():
        athlete, block, sessions = _programme()
        dates = {sessions[0].id: date(2026, 8, 12), sessions[1].id: date(2026, 8, 15)}
        result = project_athlete_scheduling(
            block,
            {},
            athlete_id=athlete.id,
            today=date(2026, 8, 11),
            planned_dates=dates,
            competitions=[CompetitionDate(9, "Summer Open", date(2026, 8, 15))],
            holiday_periods=[_holiday(athlete.id)],
        )

        assert result.sessions[0].scheduled.planned_on == date(2026, 8, 12)
        assert result.sessions[0].holiday_decision.action is SessionAction.OMIT_FROM_HOLIDAY_VIEW
        assert result.sessions[0].holiday_decision.preserve_original is True
        assert result.sessions[1].competition_ids == (9,)
        assert result.next_competition.name == "Summer Open"


def test_undated_session_does_not_invent_holiday_or_competition_membership():
    app = _app()
    with app.app_context():
        athlete, block, _ = _programme()
        result = project_athlete_scheduling(
            block, {}, athlete_id=athlete.id, today=date(2026, 8, 12),
            competitions=[CompetitionDate(2, "Open", date(2026, 8, 12))],
            holiday_periods=[_holiday(athlete.id)],
        )
        assert result.training.has_planned_dates is False
        assert result.sessions[0].holiday_decision is None
        assert result.sessions[0].competition_ids == ()


def test_overlapping_travel_constraints_require_review_instead_of_selecting_one():
    app = _app()
    with app.app_context():
        athlete, block, sessions = _programme()
        result = project_athlete_scheduling(
            block, {}, athlete_id=athlete.id, today=date(2026, 8, 12),
            planned_dates={sessions[0].id: date(2026, 8, 12)},
            holiday_periods=[
                _holiday(athlete.id, "a"),
                _holiday(athlete.id, "b", date(2026, 8, 12), date(2026, 8, 13)),
            ],
        )
        # Existing Holiday Mode conflict ordering is athlete/start/end/id.
        assert result.holiday_conflicts == (("b", "a"),)
        assert result.sessions[0].holiday_decision.action is SessionAction.COACH_REVIEW


def test_session_equipment_context_must_refer_to_the_planned_date():
    app = _app()
    with app.app_context():
        athlete, block, sessions = _programme()
        with pytest.raises(ValueError, match="must match"):
            project_athlete_scheduling(
                block, {}, athlete_id=athlete.id, today=date(2026, 8, 12),
                planned_dates={sessions[0].id: date(2026, 8, 12)},
                holiday_periods=[_holiday(athlete.id)],
                session_contexts={sessions[0].id: SessionContext(date(2026, 8, 13))},
            )


def test_checkin_timing_covers_upcoming_due_overdue_submitted_and_disabled():
    settings = AthleteCheckinSettings(
        athlete_id=1, training_enabled=True, workflow_active=True, checkin_day=2
    )
    assert project_checkin_timing(settings, (), today=date(2026, 8, 10)).state is CheckinState.UPCOMING
    assert project_checkin_timing(settings, (), today=date(2026, 8, 12)).state is CheckinState.DUE
    assert project_checkin_timing(settings, (), today=date(2026, 8, 14)).state is CheckinState.OVERDUE
    submitted = project_checkin_timing(settings, [date(2026, 8, 16)], today=date(2026, 8, 14))
    assert submitted.state is CheckinState.SUBMITTED
    assert submitted.due_on == date(2026, 8, 12)
    settings.workflow_active = False
    assert project_checkin_timing(settings, (), today=date(2026, 8, 12)).state is CheckinState.DISABLED


def test_competitions_are_sorted_and_completed_meet_is_not_next():
    result = project_athlete_scheduling(
        None, {}, athlete_id=1, today=date(2026, 8, 11),
        competitions=[
            CompetitionDate(3, "Past", date(2026, 8, 10)),
            CompetitionDate(2, "Completed", date(2026, 8, 12), "complete"),
            CompetitionDate(1, "Next", date(2026, 9, 1)),
        ],
    )
    assert [item.competition_id for item in result.competitions] == [3, 2, 1]
    assert result.next_competition.competition_id == 1
