from __future__ import annotations

import hashlib
import importlib.util
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from portal import create_app
from portal.extensions import db
from portal.sqlite_postgres_migration import (
    MigrationError,
    migrate,
    postgres_engine,
    source_engine,
    table_order,
    verify_constraints,
)


def migration_app(uri: str):
    return create_app(
        {
            "TESTING": True,
            "LEGACY_STARTUP_INITIALIZATION": False,
            "SQLALCHEMY_DATABASE_URI": uri,
        }
    )


def make_source(path: Path, *, representative: bool = False) -> None:
    app = migration_app(f"sqlite:///{path}")
    with app.app_context():
        db.create_all()
        if representative:
            now = datetime(2025, 2, 3, 12, 30, tzinfo=UTC)
            connection = db.session.connection()
            connection.execute(
                db.metadata.tables["athletes"].insert(),
                {
                    "id": 41,
                    "created_at": now,
                    "updated_at": now,
                    "first_name": "Ada",
                    "last_name": "Lifter",
                    "email": "ada@example.test",
                    "instagram": None,
                    "status": "active",
                    "bodyweight_kg": 63.25,
                    "weight_class": None,
                    "federation": "IPF",
                    "next_competition": None,
                    "coach_notes": "Preserve me",
                },
            )
            connection.execute(
                db.metadata.tables["training_blocks"].insert(),
                {
                    "id": 51,
                    "athlete_id": 41,
                    "name": "Strength",
                    "objective": None,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                },
            )
            connection.execute(
                db.metadata.tables["training_weeks"].insert(),
                {
                    "id": 61,
                    "block_id": 51,
                    "name": "Week 1",
                    "position": 7,
                    "notes": None,
                },
            )
            connection.execute(
                db.metadata.tables["training_sessions"].insert(),
                {
                    "id": 71,
                    "week_id": 61,
                    "name": "Day 1",
                    "day_label": None,
                    "position": 3,
                    "notes": None,
                },
            )
            connection.execute(
                db.metadata.tables["exercise_prescriptions"].insert(),
                {
                    "id": 81,
                    "session_id": 71,
                    "exercise_name": "Squat",
                    "position": 9,
                    "sets": 3,
                    "reps": "5",
                    "rpe": 7.5,
                    "amrap": None,
                },
            )
            connection.execute(
                db.metadata.tables["weekly_checkins"].insert(),
                {
                    "id": 91,
                    "athlete_id": 41,
                    "week_ending": date(2025, 2, 9),
                    "training_included": True,
                    "nutrition_included": False,
                    "pain_present": None,
                    "status": "submitted",
                    "submitted_at": now,
                },
            )
            connection.execute(
                db.metadata.tables["nutrition_checkins"].insert(),
                {
                    "id": 101,
                    "athlete_id": 41,
                    "submitted_at": now,
                    "bodyweight_kg": None,
                    "nutrition_adherence": 8,
                    "hunger": 4,
                    "energy": 7,
                    "sleep_quality": 6,
                    "stress": 3,
                    "digestion": 8,
                    "training_performance": 9,
                    "wins": None,
                    "reviewed": False,
                },
            )
            connection.execute(
                db.metadata.tables["exercises"].insert(),
                {
                    "id": 111,
                    "name": "Squat",
                    "movement": "squat",
                    "category": "main",
                    "fatigue_rating": 4,
                    "active": True,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            db.session.commit()


def test_invalid_source_and_target_write_failure_reports(tmp_path: Path):
    app = migration_app(f"sqlite:///{tmp_path / 'app.db'}")
    with app.app_context():
        report = tmp_path / "missing.json"
        with pytest.raises(MigrationError, match="does not exist"):
            migrate(
                source=tmp_path / "missing.db",
                target="postgresql://localhost/test",
                report_path=report,
                metadata=db.metadata,
                dry_run=True,
            )
        assert '"status": "failed"' in report.read_text()

        source = tmp_path / "source.db"
        make_source(source)
        with pytest.raises(MigrationError, match="must use PostgreSQL"):
            migrate(
                source=source,
                target="sqlite:///target.db",
                report_path=tmp_path / "invalid-target.json",
                metadata=db.metadata,
                dry_run=True,
            )


def test_read_only_source_preserves_file_and_dependency_order(tmp_path: Path):
    source = tmp_path / "history.db"
    make_source(source, representative=True)
    before = hashlib.sha256(source.read_bytes()).digest()
    app = migration_app(f"sqlite:///{tmp_path / 'metadata.db'}")
    with app.app_context(), source_engine(source).connect() as connection:
        tables = table_order(db.metadata)
        names = [table.name for table in tables]
        assert names.index("athletes") < names.index("training_blocks")
        assert names.index("training_blocks") < names.index("training_weeks")
        checks = verify_constraints(connection, tables)
        assert checks["foreign_keys_valid"]
        assert checks["unique_constraints_valid"]
    assert hashlib.sha256(source.read_bytes()).digest() == before


def test_postgres_url_validation_does_not_connect():
    if importlib.util.find_spec("psycopg") is None:
        pytest.skip("psycopg is not installed")
    engine = postgres_engine("postgresql://user:secret@db.example/test")
    try:
        assert engine.url.password == "secret"
        assert engine.url.drivername == "postgresql+psycopg"
    finally:
        engine.dispose()


@pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_DATABASE_URL")
    or importlib.util.find_spec("psycopg") is None,
    reason="POSTGRES_TEST_DATABASE_URL or psycopg is not configured",
)
def test_full_migration_dry_run_refusal_replace_rollback_and_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    base_url = os.environ["POSTGRES_TEST_DATABASE_URL"]
    schema = f"migration_test_{os.getpid()}"
    base_engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
    with base_engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    separator = "&" if "?" in base_url else "?"
    target_url = f"{base_url}{separator}options=-csearch_path%3D{schema}"
    source = tmp_path / "source.db"
    make_source(source, representative=True)
    source_hash = hashlib.sha256(source.read_bytes()).digest()
    target_app = migration_app(target_url)
    try:
        runner = target_app.test_cli_runner()
        assert runner.invoke(args=["db", "upgrade"]).exit_code == 0
        with target_app.app_context():
            dry_report = migrate(
                source=source,
                target=target_url,
                report_path=tmp_path / "dry.json",
                metadata=db.metadata,
                dry_run=True,
            )
            assert dry_report["status"] == "dry-run-complete"
            result = migrate(
                source=source,
                target=target_url,
                report_path=tmp_path / "result.json",
                metadata=db.metadata,
            )
            assert result["inserted_row_counts"]["athletes"] == 1
            assert result["verification_results"]["target"]["row_counts_valid"]
            assert result["sequence_reset_results"]["athletes"]["maximum_id"] == 41

            with pytest.raises(MigrationError, match="allow-non-empty"):
                migrate(
                    source=source,
                    target=target_url,
                    report_path=tmp_path / "refused.json",
                    metadata=db.metadata,
                )

            import portal.sqlite_postgres_migration as module

            original = module.representative_reads
            monkeypatch.setattr(
                module,
                "representative_reads",
                lambda *_args: (_ for _ in ()).throw(RuntimeError("forced failure")),
            )
            with pytest.raises(RuntimeError, match="forced failure"):
                migrate(
                    source=source,
                    target=target_url,
                    report_path=tmp_path / "rollback.json",
                    metadata=db.metadata,
                    allow_non_empty=True,
                    replace_existing=True,
                )
            monkeypatch.setattr(module, "representative_reads", original)
            with create_engine(target_url).connect() as connection:
                athlete = (
                    connection.execute(db.metadata.tables["athletes"].select())
                    .mappings()
                    .one()
                )
                assert athlete["id"] == 41
                assert athlete["instagram"] is None
        assert hashlib.sha256(source.read_bytes()).digest() == source_hash
    finally:
        with base_engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base_engine.dispose()
