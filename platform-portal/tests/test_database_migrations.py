from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from portal import create_app
from portal.extensions import db
from portal.models.exercise_library import DayTemplate, Exercise

EXPECTED_TABLES = {
    "athlete_constraint_flags",
    "athlete_checkin_settings",
    "athlete_state_facts",
    "athlete_state_overrides",
    "athlete_state_recommendations",
    "athlete_state_signals",
    "athletes",
    "coaching_applications",
    "coach_technical_observations",
    "day_template_exercises",
    "day_templates",
    "exercise_prescriptions",
    "exercises",
    "lead_captures",
    "meet_entries",
    "meet_lifts",
    "meets",
    "nutrition_checkins",
    "nutrition_provider_connections",
    "nutrition_import_jobs",
    "daily_nutrition",
    "platform_snapshots",
    "programming_lift_slots",
    "training_blocks",
    "training_sessions",
    "training_session_logs",
    "training_set_results",
    "training_weeks",
    "users",
    "weekly_checkins",
}


def migration_app(database_uri: str):
    return create_app(
        {
            "TESTING": True,
            "LEGACY_STARTUP_INITIALIZATION": False,
            "SQLALCHEMY_DATABASE_URI": database_uri,
        }
    )


def test_app_creates_without_mutating_sqlite_schema(tmp_path: Path):
    database_path = tmp_path / "startup.db"
    app = migration_app(f"sqlite:///{database_path}")

    with app.app_context():
        assert inspect(db.engine).get_table_names() == []


def test_migration_metadata_contains_all_coaching_tables(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'metadata.db'}")

    with app.app_context():
        assert set(db.metadata.tables) == EXPECTED_TABLES


def test_migration_cli_can_inspect_heads_with_local_validation_config(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'heads.db'}")

    result = app.test_cli_runner().invoke(args=["db", "heads"])

    assert result.exit_code == 0, result.output


def test_upgrade_and_schema_verification_on_empty_sqlite(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'upgrade.db'}")
    runner = app.test_cli_runner()

    upgrade = runner.invoke(args=["db", "upgrade"])
    assert upgrade.exit_code == 0, upgrade.output

    verification = runner.invoke(args=["verify-schema"])
    assert verification.exit_code == 0, verification.output

    with app.app_context():
        assert EXPECTED_TABLES <= set(inspect(db.engine).get_table_names())
        exercise_columns = {
            column["name"] for column in inspect(db.engine).get_columns("exercises")
        }
        assert {
            "lift_family",
            "movement_pattern",
            "specificity",
            "technical_purposes",
            "equipment_options",
            "constraint_tags",
            "variation_of",
            "swap_group",
        } <= exercise_columns


def test_athlete_state_upgrade_preserves_existing_athletes(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'existing.db'}")
    runner = app.test_cli_runner()
    assert (
        runner.invoke(args=["db", "upgrade", "0008_athlete_training_logs"]).exit_code
        == 0
    )
    with app.app_context():
        db.session.execute(text(
            "INSERT INTO athletes "
            "(created_at, updated_at, first_name, last_name, email, status) "
            "VALUES ('2026-01-01', '2026-01-01', 'Existing', 'Athlete', "
            "'existing@example.test', 'active')"
        ))
        db.session.commit()

    upgrade = runner.invoke(args=["db", "upgrade"])
    assert upgrade.exit_code == 0, upgrade.output
    with app.app_context():
        assert (
            db.session.execute(
                text("SELECT email FROM athletes WHERE email = 'existing@example.test'")
            ).scalar_one()
            == "existing@example.test"
        )


def test_programming_v7_upgrade_preserves_legacy_prescriptions(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'v6-programming.db'}")
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade", "0009"]).exit_code == 0
    with app.app_context():
        db.session.execute(text(
            "INSERT INTO athletes "
            "(id, created_at, updated_at, first_name, last_name, email, status) "
            "VALUES (1, '2026-01-01', '2026-01-01', 'Legacy', 'Lifter', "
            "'legacy@example.test', 'active')"
        ))
        db.session.execute(text(
            "INSERT INTO training_blocks "
            "(id, athlete_id, name, status, created_at, updated_at) "
            "VALUES (1, 1, 'V6 Block', 'draft', '2026-01-01', '2026-01-01')"
        ))
        db.session.execute(text(
            "INSERT INTO training_weeks (id, block_id, name, position) "
            "VALUES (1, 1, 'Week 1', 1)"
        ))
        db.session.execute(text(
            "INSERT INTO training_sessions (id, week_id, name, position) "
            "VALUES (1, 1, 'Legacy day', 1)"
        ))
        db.session.execute(text(
            "INSERT INTO exercises "
            "(id, name, movement, category, fatigue_rating, active, created_at, updated_at) "
            "VALUES (1, 'Competition Squat', 'squat', 'competition', 5, 1, "
            "'2026-01-01', '2026-01-01')"
        ))
        db.session.execute(text(
            "INSERT INTO exercise_prescriptions "
            "(id, session_id, exercise_name, position, sets, reps, rpe) "
            "VALUES (1, 1, 'Competition Squat', 1, 3, '5', 6)"
        ))
        db.session.commit()

    upgrade = runner.invoke(args=["db", "upgrade"])
    assert upgrade.exit_code == 0, upgrade.output
    with app.app_context():
        row = db.session.execute(text(
            "SELECT exercise_name, sets, reps, rpe, exercise_id, lift_slot_id, "
            "slot_role, rpe_min, rpe_max, provenance "
            "FROM exercise_prescriptions WHERE id = 1"
        )).mappings().one()
        assert dict(row) == {
            "exercise_name": "Competition Squat",
            "sets": 3,
            "reps": "5",
            "rpe": 6.0,
            "exercise_id": 1,
            "lift_slot_id": None,
            "slot_role": None,
            "rpe_min": None,
            "rpe_max": None,
            "provenance": None,
        }


def test_programming_seed_command_is_idempotent(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'seed.db'}")
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade"]).exit_code == 0

    assert runner.invoke(args=["seed-programming"]).exit_code == 0
    assert runner.invoke(args=["seed-programming"]).exit_code == 0

    with app.app_context():
        assert Exercise.query.count() == 3
        assert DayTemplate.query.count() == 6


def test_upgrade_on_empty_postgresql_when_available(monkeypatch):
    database_uri = os.getenv("POSTGRES_TEST_DATABASE_URL")
    if not database_uri:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not configured")

    monkeypatch.setenv("DATABASE_URL", database_uri)
    app = create_app(
        {
            "TESTING": True,
            "LEGACY_STARTUP_INITIALIZATION": False,
        }
    )
    with app.app_context():
        existing_tables = set(inspect(db.engine).get_table_names())
    assert not existing_tables, "PostgreSQL migration test requires an empty database"

    runner = app.test_cli_runner()
    upgrade = runner.invoke(args=["db", "upgrade"])
    assert upgrade.exit_code == 0, upgrade.output
    verification = runner.invoke(args=["verify-schema"])
    assert verification.exit_code == 0, verification.output
