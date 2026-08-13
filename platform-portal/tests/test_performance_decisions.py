from datetime import date, datetime

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
from portal.services.performance_decisions import build_performance_decisions


@pytest.fixture()
def app():
    instance = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with instance.app_context():
        db.create_all()
    return instance


def _athlete(email: str, **values) -> Athlete:
    item = Athlete(first_name="Alex", last_name="Lifter", email=email, **values)
    db.session.add(item)
    db.session.flush()
    return item


def _result(athlete: Athlete, *, block_name="Prep", lift="squat", load=100,
            reps=5, prescribed_reps="5", prescribed_rpe=8, actual_rpe=8,
            completed=True, skipped=False, completed_at=datetime(2026, 8, 10, 12)):
    block = TrainingBlock(athlete=athlete, name=block_name, status="active")
    week = TrainingWeek(block=block, name="Week 1")
    session = TrainingSession(week=week, name=f"{lift} day")
    slot = ProgrammingLiftSlot(session=session, lift_family=lift, position=1)
    prescription = ExercisePrescription(
        session=session, lift_slot=slot, slot_role="top_set", exercise_name=lift,
        position=1, sets=1, reps=prescribed_reps, rpe=prescribed_rpe,
    )
    log = TrainingSessionLog(
        athlete=athlete, session=session, session_name=session.name,
        block_name=block.name, week_name=week.name, status="completed",
        completed_at=completed_at,
    )
    row = TrainingSetResult(
        session_log=log, prescription=prescription, exercise_name=lift,
        exercise_position=1, set_order=1, prescribed_reps=prescribed_reps,
        prescribed_rpe=prescribed_rpe, completed=completed, skipped=skipped,
        actual_load_kg=load if completed else None,
        actual_reps=reps if completed else None, actual_rpe=actual_rpe if completed else None,
    )
    db.session.add(row)
    db.session.flush()
    return block, row


def test_summary_calculates_sourced_metrics_and_threshold_decisions(app):
    with app.app_context():
        athlete = _athlete("alex@performance.test", bodyweight_kg=82, weight_class="83 kg")
        block, first = _result(athlete, load=120, reps=5, actual_rpe=9)
        _, second = _result(
            athlete, block_name="Prep 2", load=105, reps=5, actual_rpe=9,
            completed_at=datetime(2026, 8, 11, 12),
        )
        _, missed = _result(
            athlete, block_name="Prep 3", completed=False, skipped=True,
            completed_at=datetime(2026, 8, 11, 13),
        )
        db.session.commit()

        result = build_performance_decisions(athlete.id, as_of=date(2026, 8, 11))

        assert result is not None
        metrics = {item.key: item for item in result.metrics}
        assert metrics["set_completion_rate"].value == pytest.approx(2 / 3, rel=1e-3)
        assert metrics["rpe_adherence_rate"].value == 0
        assert metrics["completed_reps"].value == 10
        assert metrics["missed_reps"].value == 5
        squat = result.lifts[0]
        assert squat.volume_kg == 1125
        assert squat.previous_e1rm_kg == 140
        assert squat.latest_e1rm_kg == 122.5
        assert squat.e1rm_change_percent == -12.5
        assert {item.rule_id for item in result.decisions} == {
            "completion-below-85", "rpe-adherence-below-70", "squat-e1rm-down-3"
        }
        assert metrics["rpe_adherence_rate"].source_refs == (
            f"training_set_result:{first.id}:actual_rpe,prescribed_rpe",
            f"training_set_result:{second.id}:actual_rpe,prescribed_rpe",
        )


def test_block_and_athlete_scope_prevent_cross_athlete_evidence(app):
    with app.app_context():
        alex = _athlete("alex@scope.test")
        beth = _athlete("beth@scope.test")
        selected, alex_row = _result(alex, block_name="Selected", load=100)
        _result(alex, block_name="Other", load=200)
        _result(beth, block_name="Private", load=300)
        db.session.commit()

        result = build_performance_decisions(
            alex.id, as_of=date(2026, 8, 11), block_id=selected.id
        )

        assert result is not None
        assert result.block_name == "Selected"
        assert result.lifts[0].volume_kg == 500
        assert result.lifts[0].source_refs == (f"training_set_result:{alex_row.id}",)
        assert build_performance_decisions(
            alex.id, as_of=date(2026, 8, 11), block_id=beth.training_blocks[0].id
        ) is None


def test_incomplete_history_is_not_fabricated(app):
    with app.app_context():
        athlete = _athlete("incomplete@performance.test")
        block = TrainingBlock(athlete=athlete, name="Empty", status="active")
        db.session.add(block)
        db.session.commit()

        result = build_performance_decisions(athlete.id, as_of=date(2026, 8, 11))

        assert result is not None
        assert result.metrics == ()
        assert result.decisions == ()
        assert all(lift.latest_e1rm_kg is None and lift.volume_kg == 0 for lift in result.lifts)
        assert "No completed set results" in result.limitations[0]


def test_partial_session_and_invalid_loading_cannot_trigger_decisions(app):
    with app.app_context():
        athlete = _athlete("partial@performance.test")
        _, completed = _result(athlete, load=100, reps=5, actual_rpe=10)
        db.session.add(TrainingSetResult(
            session_log=completed.session_log, prescription=completed.prescription,
            exercise_name="squat", exercise_position=1, set_order=2,
            prescribed_reps="5", prescribed_rpe=8, completed=False, skipped=False,
        ))
        _result(
            athlete, block_name="Invalid", load=0, reps=5,
            completed_at=datetime(2026, 8, 11, 12),
        )
        db.session.commit()

        result = build_performance_decisions(athlete.id, as_of=date(2026, 8, 11))

        assert result is not None
        assert result.lifts[0].volume_kg == 0
        assert result.lifts[0].latest_e1rm_kg is None
        assert {item.rule_id for item in result.decisions} == {"no-threshold-triggered"}
        assert "e1RM comparisons" not in result.decisions[0].evidence
        assert any("partially logged session" in note for note in result.limitations)
        assert any("positive actual load" in note for note in result.limitations)


@pytest.mark.parametrize("window_days", [0, 732])
def test_decision_window_is_bounded(app, window_days):
    with app.app_context():
        athlete = _athlete(f"bounds-{window_days}@performance.test")
        db.session.commit()
        with pytest.raises(ValueError, match="between 1 and 731"):
            build_performance_decisions(
                athlete.id, as_of=date(2026, 8, 11), window_days=window_days
            )
