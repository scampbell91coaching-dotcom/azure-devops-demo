from datetime import date, datetime

import pytest
from sqlalchemy import event

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.checkins import WeeklyCheckin
from portal.models.meet_day import Meet, MeetEntry
from portal.models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from portal.services.athlete_performance import get_athlete_performance


@pytest.fixture()
def app():
    result = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with result.app_context():
        db.create_all()
    return result


def _athlete(name="Alex"):
    item = Athlete(first_name=name, last_name="Lifter", email=f"{name}@test")
    db.session.add(item)
    db.session.flush()
    return item


def _logged_set(athlete, *, block_name="Peak", lift="squat", role="top_set", **values):
    block = TrainingBlock(athlete_id=athlete.id, name=block_name, status="active")
    week = TrainingWeek(block=block, name="Week 1", position=1)
    session = TrainingSession(week=week, name="Day 1", position=1)
    slot = ProgrammingLiftSlot(session=session, position=1, lift_family=lift)
    prescription = ExercisePrescription(
        session=session,
        lift_slot=slot,
        slot_role=role,
        exercise_name=lift.title(),
        position=1,
        sets=1,
        reps="5",
        rpe=8,
    )
    log = TrainingSessionLog(
        athlete_id=athlete.id,
        session=session,
        session_name=session.name,
        block_name=block.name,
        week_name=week.name,
        status="completed",
        completed_at=datetime(2026, 8, 10, 12),
    )
    result = TrainingSetResult(
        session_log=log,
        prescription=prescription,
        exercise_name=prescription.exercise_name,
        exercise_position=1,
        set_order=1,
        prescribed_reps=values.pop("prescribed_reps", "5"),
        prescribed_rpe=values.pop("prescribed_rpe", 8),
        completed=values.pop("completed", True),
        skipped=values.pop("skipped", False),
        actual_load_kg=values.pop("actual_load_kg", 120),
        actual_reps=values.pop("actual_reps", 5),
        actual_rpe=values.pop("actual_rpe", 8.5),
        **values,
    )
    db.session.add(log)
    db.session.flush()
    return block, result


def test_builds_canonical_chart_contract_and_explainable_decisions(app):
    with app.app_context():
        athlete = _athlete()
        block, _ = _logged_set(athlete, actual_reps=3, actual_rpe=9)
        db.session.add(
            WeeklyCheckin(
                athlete_id=athlete.id,
                week_ending=date(2026, 8, 9),
                average_bodyweight_kg=83.2,
            )
        )
        meet = Meet(
            name="Autumn Open",
            meet_date=date(2026, 8, 30),
            status="planned",
            weight_class="83 kg",
        )
        meet.entries.append(MeetEntry(athlete_id=athlete.id, flight=1, platform_order=1))
        db.session.add(meet)
        db.session.commit()

        dashboard = get_athlete_performance(
            athlete.id, today=date(2026, 8, 11), block_id=block.id
        )

        assert dashboard is not None
        assert dashboard.e1rm_trend[0].value == 132.0
        assert dashboard.volume_trend[0].value == 360.0
        assert dashboard.rpe_trend[0].delta == 1
        assert dashboard.rpe_adherence.rate == 0
        assert dashboard.reps.completed == 3
        assert dashboard.reps.missed == 2
        assert dashboard.top_set_performance == dashboard.e1rm_trend
        assert dashboard.bodyweight_trend[0].value_kg == 83.2
        assert dashboard.meet.days_remaining == 19
        assert dashboard.meet.distance_to_class_kg == 0.2
        assert [item.level for item in dashboard.decisions] == ["attention", "attention"]
        assert dashboard.decisions[0].evidence == ("2 missed reps",)


def test_never_crosses_athlete_or_block_boundaries(app):
    with app.app_context():
        athlete_a = _athlete("A")
        athlete_b = _athlete("B")
        block_a, _ = _logged_set(athlete_a, actual_load_kg=100)
        block_b, _ = _logged_set(athlete_b, actual_load_kg=300)
        db.session.commit()

        dashboard = get_athlete_performance(athlete_a.id, block_id=block_a.id)

        assert [point.value for point in dashboard.e1rm_trend] == [116.7]
        assert {item.id for item in dashboard.blocks} == {block_a.id}
        with pytest.raises(ValueError, match="does not belong"):
            get_athlete_performance(athlete_a.id, block_id=block_b.id)


def test_incomplete_legacy_history_is_reported_not_inferred(app):
    with app.app_context():
        athlete = _athlete()
        log = TrainingSessionLog(
            athlete_id=athlete.id,
            session_name="Legacy day",
            block_name="Legacy",
            week_name="Week 1",
            status="completed",
            completed_at=datetime(2026, 8, 1),
        )
        log.results.append(
            TrainingSetResult(
                exercise_name="Competition Squat",
                exercise_position=1,
                set_order=1,
                prescribed_reps="3-5",
                completed=True,
                actual_load_kg=100,
                actual_reps=3,
                actual_rpe=8,
            )
        )
        db.session.add(log)
        db.session.commit()

        dashboard = get_athlete_performance(athlete.id)

        assert dashboard.e1rm_trend == ()
        assert dashboard.reps.completed == 0
        assert dashboard.availability.e1rm.status == "unavailable"
        assert dashboard.availability.e1rm.excluded == 1
        assert dashboard.decisions[0].level == "insufficient_data"


def test_query_count_is_constant_as_training_history_grows(app):
    with app.app_context():
        athlete = _athlete()
        _logged_set(athlete)
        db.session.commit()
        athlete_id = athlete.id

        statements = []

        def record(_conn, _cursor, statement, _params, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", record)
        try:
            db.session.expire_all()
            get_athlete_performance(athlete_id)
            short_count = len(statements)
            statements.clear()
            for number in range(8):
                _logged_set(athlete, block_name=f"Block {number}")
            db.session.commit()
            db.session.expire_all()
            get_athlete_performance(athlete_id)
            long_count = len(statements)
        finally:
            event.remove(db.engine, "before_cursor_execute", record)

        assert long_count == short_count
