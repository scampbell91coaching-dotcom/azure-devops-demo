from datetime import UTC, date, datetime

import pytest

from portal import create_app
from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.athlete_state import (
    AthleteConstraintFlag, AthleteStateOverride, CoachTechnicalObservation,
)
from portal.models.checkins import WeeklyCheckin
from portal.models.programming import TrainingSessionLog, TrainingSetResult
from portal.services.athlete_state import (
    calculate_signals, latest_facts, persist_signal_snapshot, record_fact,
)


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with instance.app_context():
        db.create_all()
    return instance


def _athlete():
    athlete = Athlete(first_name="Alex", last_name="Lifter", email="alex@state.test")
    db.session.add(athlete)
    db.session.flush()
    return athlete


def test_fact_revisions_retain_provenance_and_only_latest_is_current(app):
    with app.app_context():
        athlete = _athlete()
        original = record_fact(athlete_id=athlete.id, fact_type="training_days_per_week", value=3,
                               source_type="athlete", source_ref="intake:12")
        db.session.flush()
        replacement = record_fact(athlete_id=athlete.id, fact_type="training_days_per_week", value=4,
                                  source_type="coach", recorded_by="coach:7", supersedes=original)
        db.session.commit()

        current = latest_facts(athlete.id)["training_days_per_week"]
        assert current.id == replacement.id
        assert current.value_json == 4
        assert original.source_ref == "intake:12"


def test_fact_service_rejects_invalid_or_invented_shapes(app):
    with app.app_context():
        athlete = _athlete()
        with pytest.raises(ValueError):
            record_fact(athlete_id=athlete.id, fact_type="training_days_per_week",
                        value="often", source_type="coach")
        with pytest.raises(ValueError):
            record_fact(athlete_id=athlete.id, fact_type="unknown_metric",
                        value=1, source_type="coach")


def test_signals_reuse_existing_records_and_explain_denominators(app):
    with app.app_context():
        athlete = _athlete()
        athlete.next_competition = "2026-09-01"
        record_fact(athlete_id=athlete.id, fact_type="training_start_date",
                    value="2024-08-01", source_type="athlete", source_ref="intake:1")
        db.session.add(WeeklyCheckin(
            athlete=athlete, week_ending=date(2026, 8, 2), training_included=True,
            training_adherence=80, fatigue=8, recovery=4,
        ))
        log = TrainingSessionLog(
            athlete=athlete, session_name="Day 1", block_name="Base", week_name="Week 1",
            status="completed", started_at=datetime(2026, 8, 5, tzinfo=UTC),
            completed_at=datetime(2026, 8, 5, tzinfo=UTC),
        )
        db.session.add(log)
        db.session.flush()
        db.session.add_all([
            TrainingSetResult(session_log=log, exercise_name="Squat", exercise_position=1,
                              set_order=1, completed=True, prescribed_rpe=8, actual_rpe=8.5),
            TrainingSetResult(session_log=log, exercise_name="Squat", exercise_position=1,
                              set_order=2, skipped=True, prescribed_rpe=8),
        ])
        db.session.commit()

        signals = {item.signal_type: item for item in calculate_signals(athlete, as_of=date(2026, 8, 7))}
        assert signals["training_age_days"].value == 736
        assert signals["days_to_competition"].value == 25
        assert signals["logged_session_completion_rate"].value == 1.0
        assert signals["set_completion_rate"].value == 0.5
        assert signals["rpe_adherence_rate"].value == 1.0
        assert signals["reported_fatigue"].source_refs[0].startswith("weekly_checkin:")
        assert "unlogged assignments are not counted" in signals["logged_session_completion_rate"].explanation

        saved = persist_signal_snapshot(athlete, as_of=date(2026, 8, 7))
        db.session.commit()
        assert len({item.snapshot_id for item in saved}) == 1
        assert all(item.source_refs_json for item in saved)


def test_unknown_data_produces_no_signal_and_observations_stay_separate(app):
    with app.app_context():
        athlete = _athlete()
        athlete.next_competition = "Autumn regional"
        db.session.add_all([
            CoachTechnicalObservation(athlete=athlete, lift="squat", observation="Chest drops late",
                                      recorded_by="coach:7", observed_on=date(2026, 8, 1)),
            AthleteConstraintFlag(athlete=athlete, flag_kind="irritation", label="Knee irritation",
                                  reported_by="athlete", starts_on=date(2026, 8, 1)),
            AthleteStateOverride(athlete=athlete, target_type="signal", target_ref="training_frequency",
                                 override_json={"value": 3}, reason="Temporary travel schedule",
                                 recorded_by="coach:7"),
        ])
        db.session.commit()

        assert calculate_signals(athlete, as_of=date(2026, 8, 7)) == []
        assert athlete.technical_observations[0].observation == "Chest drops late"
        assert athlete.constraint_flags[0].flag_kind == "irritation"
        assert athlete.state_overrides[0].reason == "Temporary travel schedule"
