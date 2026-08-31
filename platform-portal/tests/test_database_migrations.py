from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from portal import create_app
from portal.extensions import db
from portal.models.exercise_library import DayTemplate, Exercise

EXPECTED_TABLES = {
    "account_tokens",
    "athlete_constraint_flags",
    "athlete_checkin_settings",
    "athlete_state_facts",
    "athlete_state_overrides",
    "athlete_state_recommendations",
    "athlete_state_signals",
    "athletes",
    "billing_webhook_events",
    "coaching_applications",
    "client_service_changes",
    "coach_technical_observations",
    "coach_athlete_ownerships",
    "day_template_exercises",
    "day_templates",
    "exercise_prescriptions",
    "exercises",
    "external_coaching_reviews",
    "lead_captures",
    "meet_entries",
    "meet_lifts",
    "meets",
    "meal_plan_assignments",
    "meal_plan_templates",
    "pdf_meal_plans",
    "organisations",
    "nutrition_checkins",
    "nutrition_provider_connections",
    "nutrition_import_jobs",
    "nutrition_macro_prescriptions",
    "organisation_invitations",
    "organisation_memberships",
    "daily_nutrition",
    "platform_snapshots",
    "programming_lift_slots",
    "programme_revisions",
    "training_blocks",
    "training_sessions",
    "training_session_logs",
    "training_set_results",
    "training_weeks",
    "subscription_accounts",
    "support_access_events",
    "support_capability_grants",
    "support_delegations",
    "support_principals",
    "spreadsheet_import_batches",
    "spreadsheet_import_provenance",
    "users",
    "weekly_checkins",
    "warmup_protocols",
    "warmup_protocol_steps",
    "warmup_assignments",
    "warmup_overrides",
    "warmup_plan_snapshots",
    "warmup_plan_snapshot_steps",
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
    config = Config(str(Path(__file__).parents[1] / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    assert ScriptDirectory.from_config(config).get_heads() == [
        "0029_programming_publication_safety"
    ]


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
            "auto_select",
            "lift_relevance",
            "training_phases",
            "compatibility_tags",
            "coach_priority",
        } <= exercise_columns
        lift_slot_columns = {
            column["name"] for column in inspect(db.engine).get_columns(
                "programming_lift_slots"
            )
        }
        assert "exposure_role" in lift_slot_columns


def test_0029_upgrades_an_existing_0028_database(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'upgrade-from-0028.db'}")
    runner = app.test_cli_runner()

    to_0028 = runner.invoke(
        args=["db", "upgrade", "0028_spreadsheet_import_history"]
    )
    assert to_0028.exit_code == 0, to_0028.output
    to_head = runner.invoke(args=["db", "upgrade"])
    assert to_head.exit_code == 0, to_head.output

    with app.app_context():
        columns = {
            column["name"]
            for column in inspect(db.engine).get_columns("training_blocks")
        }
        assert "replaces_block_id" in columns


def test_canonical_tenancy_migration_does_not_automatically_backfill_legacy_rows(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'no-automatic-backfill.db'}")
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade", "0019_meal_plan_delivery"]).exit_code == 0
    with app.app_context():
        db.session.execute(text(
            "INSERT INTO athletes "
            "(id, created_at, updated_at, first_name, last_name, email, status) "
            "VALUES (7, '2026-01-01', '2026-01-01', 'Legacy', 'Athlete', "
            "'legacy-member@example.test', 'active')"
        ))
        db.session.execute(text(
            "INSERT INTO users (id, email, role, athlete_id, active, created_at) VALUES "
            "(8, 'legacy-coach@example.test', 'coach', NULL, 1, '2026-01-01'), "
            "(9, 'legacy-member@example.test', 'athlete', 7, 1, '2026-01-01')"
        ))
        db.session.commit()
    upgrade = runner.invoke(args=["db", "upgrade"])
    assert upgrade.exit_code == 0, upgrade.output
    with app.app_context():
        assert db.session.execute(text("SELECT COUNT(*) FROM organisations")).scalar_one() == 0
        assert db.session.execute(text("SELECT COUNT(*) FROM organisation_memberships")).scalar_one() == 0
        assert db.session.execute(text("SELECT COUNT(*) FROM coach_athlete_ownerships")).scalar_one() == 0


def test_billing_migration_does_not_create_a_legacy_organisation_or_subscription(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'billing.db'}")
    assert app.test_cli_runner().invoke(args=["db", "upgrade"]).exit_code == 0

    with app.app_context():
        assert db.session.execute(text(
            "SELECT COUNT(*) FROM organisations"
        )).scalar_one() == 0
        assert db.session.execute(text(
            "SELECT COUNT(*) FROM subscription_accounts"
        )).scalar_one() == 0


def test_nutrition_macro_migration_enforces_overlap_and_append_only(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'nutrition-macros.db'}")
    assert app.test_cli_runner().invoke(args=["db", "upgrade"]).exit_code == 0
    with app.app_context():
        db.session.execute(text("INSERT INTO athletes (id, created_at, updated_at, first_name, last_name, email, status) VALUES (1, '2026-01-01', '2026-01-01', 'Test', 'Athlete', 'macro@example.test', 'active')"))
        db.session.execute(text("INSERT INTO users (id, email, role, active, created_at) VALUES (1, 'coach@example.test', 'coach', 1, '2026-01-01')"))
        insert = "INSERT INTO nutrition_macro_prescriptions (id, athlete_id, effective_from, effective_until, calories, protein_g, carbohydrate_g, fat_g, created_by_user_id, created_at) VALUES (:id, 1, :start, :end, 2500, 180, 300, 65, 1, '2026-01-01')"
        db.session.execute(text(insert), {"id": "first", "start": "2026-08-01", "end": "2026-08-31"})
        db.session.commit()
        with pytest.raises(IntegrityError, match="overlap"):
            db.session.execute(text(insert), {"id": "overlap", "start": "2026-08-31", "end": "2026-09-10"})
            db.session.commit()
        db.session.rollback()
        with pytest.raises(IntegrityError, match="append-only"):
            db.session.execute(text("UPDATE nutrition_macro_prescriptions SET calories = 2600 WHERE id = 'first'"))
            db.session.commit()
        db.session.rollback()


def test_accessory_intelligence_upgrade_preserves_legacy_opt_out(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'accessory-intelligence.db'}")
    runner = app.test_cli_runner()
    assert runner.invoke(args=["db", "upgrade", "0012_athlete_accounts"]).exit_code == 0
    with app.app_context():
        db.session.execute(text(
            "INSERT INTO exercises "
            "(name, movement, category, fatigue_rating, accessory_suitable, active, created_at, updated_at) "
            "VALUES ('Legacy Accessory', 'accessory', 'assistance', 3, 1, 1, "
            "'2026-01-01', '2026-01-01')"
        ))
        db.session.commit()
    upgrade = runner.invoke(args=["db", "upgrade"])
    assert upgrade.exit_code == 0, upgrade.output
    with app.app_context():
        row = db.session.execute(text(
            "SELECT auto_select, coach_priority, lift_relevance FROM exercises "
            "WHERE name = 'Legacy Accessory'"
        )).one()
        assert tuple(row) == (0, 0, None)
        user_columns = {
            column["name"]: column for column in inspect(db.engine).get_columns("users")
        }
        assert user_columns["password_hash"]["nullable"] is True
        account_columns = {
            column["name"] for column in inspect(db.engine).get_columns("account_tokens")
        }
        assert {
            "purpose", "token_digest", "expires_at", "consumed_at", "revoked_at",
            "athlete_id", "user_id", "delivery_state", "delivery_detail",
        } <= account_columns


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
    with app.app_context():
        inspector = inspect(db.engine)
        assert set(inspector.get_table_names()) == EXPECTED_TABLES | {"alembic_version"}
        heads = db.session.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        assert heads == ["0027_tenancy_ownership_expand"]
