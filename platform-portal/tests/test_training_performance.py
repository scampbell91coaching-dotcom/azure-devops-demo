from datetime import UTC, date, datetime

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
from portal.services.training_performance import training_performance_summary


@pytest.fixture()
def app():
    instance = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with instance.app_context():
        db.create_all()
    return instance


def _programme(athlete):
    block = TrainingBlock(athlete=athlete, name="Meet prep", status="active")
    week = TrainingWeek(block=block, name="Week 1", position=1)
    session = TrainingSession(week=week, name="SBD", position=1)
    slot = ProgrammingLiftSlot(session=session, position=1, lift_family="squat")
    prescriptions = [
        ExercisePrescription(session=session, lift_slot=slot, slot_role="top_set",
                             exercise_name="Competition squat", position=1, sets=1,
                             reps="3", rpe=8),
        ExercisePrescription(session=session, exercise_name="Bench", position=2,
                             sets=1, reps="5", rpe_min=7, rpe_max=8),
        ExercisePrescription(session=session, exercise_name="Deadlift", position=3,
                             sets=1, reps="4", rpe_cap=8),
        ExercisePrescription(session=session, exercise_name="Rows", position=4,
                             sets=1, reps="8-10"),
    ]
    db.session.add(block)
    db.session.flush()
    return session, prescriptions


def _result(log, prescription, *, completed=False, skipped=False, reps=None, rpe=None):
    return TrainingSetResult(
        session_log=log, prescription=prescription,
        exercise_name=prescription.exercise_name,
        exercise_position=prescription.position, set_order=1,
        prescribed_reps=prescription.reps, prescribed_rpe=prescription.rpe,
        completed=completed, skipped=skipped, actual_reps=reps, actual_rpe=rpe,
        actual_load_kg=180 if prescription.slot_role == "top_set" else None,
    )


def test_summary_explains_target_range_cap_completion_and_top_set(app):
    with app.app_context():
        athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@metrics.test")
        session, prescriptions = _programme(athlete)
        log = TrainingSessionLog(
            athlete=athlete, session=session, session_name="SBD", block_name="Meet prep",
            week_name="Week 1", status="completed",
            started_at=datetime(2026, 8, 5, tzinfo=UTC),
        )
        db.session.add_all([
            _result(log, prescriptions[0], completed=True, reps=2, rpe=8.5),
            _result(log, prescriptions[1], completed=True, reps=5, rpe=8.5),
            _result(log, prescriptions[2], skipped=True),
            _result(log, prescriptions[3], completed=True, reps=9),
        ])
        db.session.commit()

        summary = training_performance_summary(
            athlete.id, start=date(2026, 8, 1), end=date(2026, 8, 7)
        )

        assert summary.rpe.comparable_sets == 2
        assert summary.rpe.adherent_sets == 1
        assert summary.rpe.above_sets == 1
        assert summary.rpe.adherence_rate == 0.5
        assert summary.rpe.mean_variance == 0.5
        assert summary.rpe.unavailable_sets == 1
        assert summary.reps.decided_sets == 4
        assert summary.reps.completed_sets == 3
        assert summary.reps.skipped_sets == 1
        assert summary.reps.completion_rate == 0.75
        assert summary.reps.prescribed_reps == 12
        assert summary.reps.completed_reps == 7
        assert summary.reps.missed_reps == 5
        assert summary.reps.unavailable_sets == 1
        assert len(summary.top_sets) == 1
        assert summary.top_sets[0].exercise_name == "Competition squat"
        assert summary.top_sets[0].rpe_status == "adherent"


def test_summary_scopes_athlete_date_and_block_and_reports_unknown_history(app):
    with app.app_context():
        alex = Athlete(first_name="Alex", last_name="Lifter", email="alex@scope.test")
        sam = Athlete(first_name="Sam", last_name="Lifter", email="sam@scope.test")
        db.session.add_all([alex, sam])
        db.session.flush()
        for athlete, block, day in (
            (alex, "Base", datetime(2026, 8, 5, tzinfo=UTC)),
            (alex, "Meet prep", datetime(2026, 7, 1, tzinfo=UTC)),
            (sam, "Base", datetime(2026, 8, 5, tzinfo=UTC)),
        ):
            log = TrainingSessionLog(athlete=athlete, session_name="Legacy", block_name=block,
                                     week_name="Week", status="completed", started_at=day)
            db.session.add(log)
            db.session.flush()
            db.session.add(TrainingSetResult(
                session_log=log, exercise_name="Legacy squat", exercise_position=1,
                set_order=1, prescribed_reps=None, prescribed_rpe=None,
                completed=True, actual_reps=3, actual_rpe=8,
            ))
        db.session.commit()

        summary = training_performance_summary(
            alex.id, start=date(2026, 8, 1), end=date(2026, 8, 31), block_name="Base"
        )

        assert summary.reps.decided_sets == 1
        assert summary.reps.unavailable_sets == 1
        assert summary.rpe.comparable_sets == 0
        assert summary.rpe.adherence_rate is None
        assert summary.rpe.unavailable_sets == 1
        assert summary.top_sets == ()
        assert summary.top_set_unavailable == 1


def test_summary_rejects_reversed_window(app):
    with app.app_context(), pytest.raises(ValueError, match="end must be"):
        training_performance_summary(1, start=date(2026, 8, 2), end=date(2026, 8, 1))
