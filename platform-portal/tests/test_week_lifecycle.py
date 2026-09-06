from datetime import UTC, datetime

import pytest
from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from portal.models.spreadsheet_import import (
    SpreadsheetImportBatch,
    SpreadsheetImportProvenance,
)
from sqlalchemy.exc import SQLAlchemyError


def _app_with_block(week_count: int = 2):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        athlete = Athlete(
            first_name="Alex", last_name="Lifter", email="alex@example.com"
        )
        block = TrainingBlock(athlete=athlete, name="Prep")
        for position in range(1, week_count + 1):
            week = TrainingWeek(
                block=block,
                name=f"Week {position}",
                position=position,
                notes=f"week notes {position}",
            )
            session = TrainingSession(
                week=week,
                name=f"Session {position}",
                day_label="Monday",
                position=3,
                notes="session notes",
            )
            ExercisePrescription(
                session=session,
                exercise_name="Squat",
                position=4,
                prescription_type="load_capped",
                sets=4,
                reps="5",
                reps_min=3,
                reps_max=6,
                load_kg=120,
                load_cap_kg=130,
                percentage=80,
                rpe=7.5,
                rpe_cap=8.5,
                target_reps=5,
                target_rpe=8,
                target_load_kg=125,
                amrap=False,
                tempo="3010",
                rest_seconds=180,
                notes="prescription notes",
            )
        db.session.add(athlete)
        db.session.commit()
        return app, block.id


def test_add_blank_week_appends_with_contiguous_position():
    app, block_id = _app_with_block()

    response = app.test_client().post(
        f"/programming/blocks/{block_id}/weeks", data={"notes": "Easy week"}
    )

    assert response.status_code == 302
    with app.app_context():
        weeks = db.session.get(TrainingBlock, block_id).weeks
        assert [(week.name, week.position) for week in weeks] == [
            ("Week 1", 1),
            ("Week 2", 2),
            ("Week 3", 3),
        ]
        assert weeks[-1].notes == "Easy week"
        assert weeks[-1].sessions == []


def test_duplicate_week_is_adjacent_and_preserves_all_programming_fields():
    app, block_id = _app_with_block(3)
    with app.app_context():
        source_id = db.session.get(TrainingBlock, block_id).weeks[0].id

    response = app.test_client().post(f"/programming/weeks/{source_id}/duplicate")

    assert response.status_code == 302
    with app.app_context():
        weeks = db.session.get(TrainingBlock, block_id).weeks
        assert [week.position for week in weeks] == [1, 2, 3, 4]
        assert [week.name for week in weeks] == [
            "Week 1",
            "Week 1 Copy",
            "Week 2",
            "Week 3",
        ]
        source, copied = weeks[:2]
        assert copied.notes == source.notes
        assert copied.sessions[0].id != source.sessions[0].id
        assert copied.sessions[0].position == 3
        assert copied.sessions[0].day_label == "Monday"
        assert copied.sessions[0].notes == "session notes"
        source_values = source.sessions[0].prescriptions[0].copy_values()
        copied_item = copied.sessions[0].prescriptions[0]
        assert copied_item.id != source.sessions[0].prescriptions[0].id
        assert copied_item.position == 4
        assert copied_item.copy_values() == source_values


@pytest.mark.parametrize("count", [1, 3])
def test_extend_block_copies_final_week_one_or_more_times(count):
    app, block_id = _app_with_block(1)

    response = app.test_client().post(
        f"/programming/blocks/{block_id}/extend", data={"weeks": str(count)}
    )

    assert response.status_code == 302
    with app.app_context():
        weeks = db.session.get(TrainingBlock, block_id).weeks
        assert [week.position for week in weeks] == list(range(1, count + 2))
        assert all(week.sessions[0].position == 3 for week in weeks)
        assert all(week.sessions[0].prescriptions[0].position == 4 for week in weeks)
        assert all(
            week.sessions[0].prescriptions[0].prescription_type == "load_capped"
            for week in weeks
        )


def test_delete_week_cascades_and_renumbers_remaining_weeks():
    app, block_id = _app_with_block(3)
    with app.app_context():
        deleted_id = db.session.get(TrainingBlock, block_id).weeks[1].id

    response = app.test_client().post(f"/programming/weeks/{deleted_id}/delete")

    assert response.status_code == 302
    with app.app_context():
        block = db.session.get(TrainingBlock, block_id)
        assert db.session.get(TrainingWeek, deleted_id) is None
        assert [(week.name, week.position) for week in block.weeks] == [
            ("Week 1", 1),
            ("Week 3", 2),
        ]
        assert TrainingSession.query.count() == 2
        assert ExercisePrescription.query.count() == 2


def test_delete_final_remaining_week_is_rejected_safely():
    app, block_id = _app_with_block(1)
    with app.app_context():
        week_id = db.session.get(TrainingBlock, block_id).weeks[0].id

    response = app.test_client().post(f"/programming/weeks/{week_id}/delete")

    assert response.status_code == 409
    with app.app_context():
        assert TrainingWeek.query.count() == 1
        assert TrainingSession.query.count() == 1
        assert ExercisePrescription.query.count() == 1


def test_duplicate_rolls_back_all_changes_on_sqlalchemy_error(monkeypatch):
    app, block_id = _app_with_block(2)
    with app.app_context():
        source_id = db.session.get(TrainingBlock, block_id).weeks[0].id
        original_flush = db.session.flush

        def fail_flush(*args, **kwargs):
            raise SQLAlchemyError("forced failure")

        with monkeypatch.context() as patch:
            patch.setattr(db.session, "flush", fail_flush)
            with pytest.raises(SQLAlchemyError, match="forced failure"):
                app.test_client().post(f"/programming/weeks/{source_id}/duplicate")

        original_flush()
        weeks = db.session.get(TrainingBlock, block_id).weeks
        assert [(week.name, week.position) for week in weeks] == [
            ("Week 1", 1),
            ("Week 2", 2),
        ]
        assert TrainingSession.query.count() == 2
        assert ExercisePrescription.query.count() == 2


def test_completed_and_imported_history_survives_week_deletion_and_is_not_duplicated():
    app, block_id = _app_with_block(2)
    with app.app_context():
        source = db.session.get(TrainingBlock, block_id).weeks[0]
        session = source.sessions[0]
        prescription = session.prescriptions[0]
        log = TrainingSessionLog(
            athlete_id=source.block.athlete_id,
            session=session,
            session_name=session.name,
            block_name=source.block.name,
            week_name=source.name,
            status="completed",
            completed_at=datetime.now(UTC),
        )
        result = TrainingSetResult(
            session_log=log,
            prescription=prescription,
            exercise_name=prescription.exercise_name,
            exercise_position=prescription.position,
            set_order=1,
            prescribed_reps=prescription.reps,
            actual_load_kg=120,
            actual_reps=5,
            actual_rpe=8,
            completed=True,
        )
        batch = SpreadsheetImportBatch(
            athlete_id=source.block.athlete_id,
            source_filename="history.csv",
            source_checksum="a" * 64,
            rows_imported=1,
            rows_skipped_duplicate=0,
            rows_rejected=0,
        )
        provenance = SpreadsheetImportProvenance(
            athlete_id=source.block.athlete_id,
            batch=batch,
            result=result,
            source_sheet="CSV",
            source_row=2,
            semantic_fingerprint="b" * 64,
            semantic_values={"exercise": "Squat"},
        )
        db.session.add_all([log, result, batch, provenance])
        db.session.commit()
        source_id, log_id, result_id, provenance_id = source.id, log.id, result.id, provenance.id

    duplicated = app.test_client().post(f"/programming/weeks/{source_id}/duplicate")
    assert duplicated.status_code == 302
    with app.app_context():
        assert TrainingSessionLog.query.count() == 1
        assert TrainingSetResult.query.count() == 1
        assert SpreadsheetImportProvenance.query.count() == 1

    deleted = app.test_client().post(f"/programming/weeks/{source_id}/delete")
    assert deleted.status_code == 302
    with app.app_context():
        log = db.session.get(TrainingSessionLog, log_id)
        result = db.session.get(TrainingSetResult, result_id)
        assert log is not None and log.status == "completed"
        assert log.session_id is None
        assert (log.block_name, log.week_name, log.session_name) == (
            "Prep", "Week 1", "Session 1"
        )
        assert result is not None and result.prescription_id is None
        assert db.session.get(SpreadsheetImportProvenance, provenance_id).training_set_result_id == result_id


def test_week_edit_and_reorder_do_not_renumber_unrelated_history():
    app, block_id = _app_with_block(3)
    with app.app_context():
        weeks = db.session.get(TrainingBlock, block_id).weeks
        first_id, third_id = weeks[0].id, weeks[2].id

    assert app.test_client().post(
        f"/programming/weeks/{first_id}/edit",
        data={"name": "Foundation", "notes": "Technique"},
    ).status_code == 302
    assert app.test_client().post(
        f"/programming/weeks/{third_id}/reorder", data={"position": "1"}
    ).status_code == 302
    with app.app_context():
        weeks = db.session.get(TrainingBlock, block_id).weeks
        assert [(item.name, item.position) for item in weeks] == [
            ("Week 3", 1), ("Foundation", 2), ("Week 2", 3)
        ]
