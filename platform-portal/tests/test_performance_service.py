from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import (
    ExercisePrescription,
    ProgrammingLiftSlot,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from portal.services.performance import build_sbd_performance_analytics


@pytest.fixture()
def performance_app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        athletes = [
            Athlete(first_name="Alex", last_name="One", email="alex@example.com"),
            Athlete(first_name="Sam", last_name="Two", email="sam@example.com"),
        ]
        db.session.add_all(athletes)
        db.session.flush()
        app.config["ATHLETE_IDS"] = tuple(item.id for item in athletes)
        db.session.commit()
    return app


def _add_set(
    athlete_id,
    *,
    block_name,
    completed_at,
    family="squat",
    role="top_set",
    load=150,
    reps=3,
    completed=True,
    status="completed",
):
    block = TrainingBlock(athlete_id=athlete_id, name=block_name, status="active")
    week = TrainingWeek(block=block, name="Week", position=1)
    session = TrainingSession(week=week, name="Session", position=1)
    slot = ProgrammingLiftSlot(session=session, position=1, lift_family=family)
    prescription = ExercisePrescription(
        session=session, lift_slot=slot, slot_role=role, exercise_name=family,
        position=1, sets=1, reps=str(reps),
    )
    log = TrainingSessionLog(
        athlete_id=athlete_id, session=session, session_name="Session",
        block_name=block_name, week_name="Week", status=status,
        completed_at=completed_at if status == "completed" else None,
    )
    result = TrainingSetResult(
        session_log=log, prescription=prescription, exercise_name=family,
        exercise_position=1, set_order=1, completed=completed,
        actual_load_kg=load, actual_reps=reps, actual_rpe=8,
    )
    db.session.add_all([block, log])
    db.session.flush()
    return block, result


def test_calculates_best_top_set_e1rm_and_all_sbd_volume(performance_app):
    with performance_app.app_context():
        athlete_id = performance_app.config["ATHLETE_IDS"][0]
        block, _ = _add_set(
            athlete_id, block_name="Prep", completed_at=datetime(2026, 8, 1, 9, tzinfo=UTC)
        )
        # Back-off work contributes volume, but cannot become the top-set trend.
        _, backoff = _add_set(
            athlete_id, block_name="Other", completed_at=datetime(2026, 8, 2, 9, tzinfo=UTC),
            family="bench", role="back_off", load=100, reps=5,
        )
        # A second top set in the same session selects the higher e1RM deterministically.
        log = TrainingSessionLog.query.filter_by(session_id=block.weeks[0].sessions[0].id).one()
        first = log.results[0]
        extra = TrainingSetResult(
            session_log=log, prescription=first.prescription, exercise_name="squat",
            exercise_position=1, set_order=2, is_extra=True, completed=True,
            actual_load_kg=140, actual_reps=5, actual_rpe=9,
        )
        db.session.add(extra)
        db.session.commit()

        result = build_sbd_performance_analytics(athlete_id)

        assert [(p.lift_family, p.e1rm_kg, p.reps) for p in result.e1rm_trend] == [
            ("squat", Decimal("165.00"), 3)
        ]
        assert [(p.lift_family, p.volume_kg, p.completed_sets) for p in result.training_volume] == [
            ("squat", Decimal("1150.00"), 2),
            ("bench", Decimal("500.00"), 1),
        ]
        assert backoff.id is not None


def test_filters_by_owned_block_and_inclusive_dates(performance_app):
    with performance_app.app_context():
        alex, sam = performance_app.config["ATHLETE_IDS"]
        kept, _ = _add_set(alex, block_name="Kept", completed_at=datetime(2026, 8, 2, 23, 59))
        _add_set(alex, block_name="Old", completed_at=datetime(2026, 8, 1, 12))
        foreign, _ = _add_set(sam, block_name="Private", completed_at=datetime(2026, 8, 2, 12))
        db.session.commit()

        result = build_sbd_performance_analytics(
            alex, block_id=kept.id, date_from=date(2026, 8, 2), date_to=date(2026, 8, 2)
        )
        assert len(result.e1rm_trend) == 1
        assert result.e1rm_trend[0].performed_on == date(2026, 8, 2)
        with pytest.raises(ValueError, match="does not belong"):
            build_sbd_performance_analytics(alex, block_id=foreign.id)
        with pytest.raises(ValueError, match="date_from"):
            build_sbd_performance_analytics(
                alex, date_from=date(2026, 8, 3), date_to=date(2026, 8, 2)
            )


def test_missing_history_is_explicit_and_never_inferred_from_name(performance_app):
    with performance_app.app_context():
        athlete_id = performance_app.config["ATHLETE_IDS"][0]
        block, result = _add_set(
            athlete_id, block_name="Legacy", completed_at=datetime(2026, 8, 2, 12)
        )
        result.prescription = None
        result.exercise_name = "Competition squat"
        db.session.commit()

        analytics = build_sbd_performance_analytics(athlete_id)
        assert analytics.e1rm_trend == ()
        assert analytics.training_volume == ()
        assert analytics.data_quality.sets_missing_lift_family == 1
        assert "excluded" in analytics.data_quality.notes[0]
        assert block.id is not None


def test_high_rep_top_set_only_contributes_volume_and_partial_logs_are_ignored(performance_app):
    with performance_app.app_context():
        athlete_id = performance_app.config["ATHLETE_IDS"][0]
        _add_set(
            athlete_id, block_name="Volume", completed_at=datetime(2026, 8, 2, 12),
            family="deadlift", load=80, reps=13,
        )
        _add_set(
            athlete_id, block_name="Draft", completed_at=datetime(2026, 8, 3, 12),
            status="in_progress", load=200, reps=1,
        )
        db.session.commit()

        analytics = build_sbd_performance_analytics(athlete_id)
        assert analytics.e1rm_trend == ()
        assert analytics.training_volume[0].volume_kg == Decimal("1040.00")
        assert analytics.data_quality.top_sets_outside_e1rm_rep_range == 1
