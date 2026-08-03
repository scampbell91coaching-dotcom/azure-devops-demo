from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import inspect

from portal import create_app
from portal.extensions import db
from portal.models.exercise_library import DayTemplate, Exercise

EXPECTED_TABLES = {
    "athlete_checkin_settings",
    "athletes",
    "coaching_applications",
    "day_template_exercises",
    "day_templates",
    "exercise_prescriptions",
    "exercises",
    "lead_captures",
    "nutrition_checkins",
    "platform_snapshots",
    "training_blocks",
    "training_sessions",
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


def test_upgrade_and_schema_verification_on_empty_sqlite(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'upgrade.db'}")
    runner = app.test_cli_runner()

    upgrade = runner.invoke(args=["db", "upgrade"])
    assert upgrade.exit_code == 0, upgrade.output

    verification = runner.invoke(args=["verify-schema"])
    assert verification.exit_code == 0, verification.output

    with app.app_context():
        assert EXPECTED_TABLES <= set(inspect(db.engine).get_table_names())


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
