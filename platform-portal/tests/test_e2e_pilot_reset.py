from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from portal import create_app
from portal.extensions import db
from portal.models.account_token import AccountToken
from portal.models.checkins import AthleteCheckinSettings, WeeklyCheckin
from portal.models.programming import TrainingBlock, TrainingSessionLog, TrainingSetResult
from portal.models.user import User, UserRole
from portal.models.warmup import WarmupOverride, WarmupPlanSnapshot, WarmupPlanSnapshotStep

SUPPORT = Path(__file__).resolve().parents[2] / "e2e" / "support"
sys.path.insert(0, str(SUPPORT))
from seed_database import reset_pilot_fixture, seed_database  # noqa: E402


def test_reset_pilot_fixture_restores_mutable_state_without_touching_other_athletes():
    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": False,
            "SECRET_KEY": "pilot-reset-test-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with app.app_context():
        seed_database(app)
        alex_user_id = User.query.filter_by(athlete_id=101).one().id
        alex_block_status = db.session.get(TrainingBlock, 301).status

        pilot_user = User(
            email="taylor.pilot@example.test",
            role=UserRole.ATHLETE,
            athlete_id=303,
            active=True,
        )
        pilot_user.set_password("Pilot Athlete password!")
        db.session.add(pilot_user)
        db.session.flush()
        db.session.add(
            AccountToken(
                purpose="invitation",
                token_digest="a" * 64,
                athlete_id=303,
                user_id=pilot_user.id,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )

        pilot_block = db.session.get(TrainingBlock, 601)
        pilot_block.status = "active"
        log = TrainingSessionLog(
            athlete_id=303,
            session_id=801,
            session_name="mutated",
            block_name="mutated",
            week_name="mutated",
            status="completed",
        )
        log.results.append(
            TrainingSetResult(
                exercise_name="Competition Squat",
                exercise_position=1,
                set_order=1,
                completed=True,
                actual_load_kg=122.5,
                actual_reps=3,
                actual_rpe=8,
            )
        )
        alex_log = TrainingSessionLog(
            athlete_id=101,
            session_id=501,
            session_name="Squat day",
            block_name="Deterministic strength block",
            week_name="Foundation week",
            status="in_progress",
        )
        alex_log.results.append(
            TrainingSetResult(
                exercise_name="Competition Squat",
                exercise_position=1,
                set_order=1,
            )
        )
        db.session.add_all([log, alex_log])

        snapshot = WarmupPlanSnapshot(athlete_id=303, session_id=801)
        snapshot.steps.append(
            WarmupPlanSnapshotStep(
                position=1,
                phase=10,
                name="Mutated warm-up",
                kind="duration",
                sets=1,
                duration_seconds=60,
                source_type="override",
                source_key="mutated",
            )
        )
        db.session.add_all(
            [
                snapshot,
                WarmupOverride(
                    athlete_id=303,
                    session_id=801,
                    action="append",
                    phase=10,
                    name="Mutated override",
                    kind="duration",
                    sets=1,
                    duration_seconds=60,
                    reason="test mutation",
                ),
                AthleteCheckinSettings(athlete_id=303, checkin_day=2),
                WeeklyCheckin(athlete_id=303, week_ending=date.today()),
            ]
        )
        db.session.commit()

        reset_pilot_fixture()
        reset_pilot_fixture()

        assert User.query.filter_by(athlete_id=303).count() == 0
        assert AccountToken.query.filter_by(athlete_id=303).count() == 0
        assert db.session.get(TrainingBlock, 601).status == "draft"
        assert TrainingSessionLog.query.filter_by(athlete_id=303, session_id=801).count() == 0
        assert TrainingSetResult.query.join(TrainingSessionLog).filter(
            TrainingSessionLog.athlete_id == 303
        ).count() == 0
        assert WarmupPlanSnapshot.query.filter_by(athlete_id=303, session_id=801).count() == 0
        assert WarmupPlanSnapshotStep.query.count() == 0
        assert WarmupOverride.query.filter_by(athlete_id=303, session_id=801).count() == 0
        assert AthleteCheckinSettings.query.filter_by(athlete_id=303).count() == 0
        assert WeeklyCheckin.query.filter_by(athlete_id=303).count() == 0

        assert User.query.filter_by(athlete_id=101).one().id == alex_user_id
        assert db.session.get(TrainingBlock, 301).status == alex_block_status
        assert TrainingSessionLog.query.filter_by(athlete_id=101, session_id=501).count() == 1
        assert TrainingSetResult.query.join(TrainingSessionLog).filter(
            TrainingSessionLog.athlete_id == 101
        ).count() == 1
