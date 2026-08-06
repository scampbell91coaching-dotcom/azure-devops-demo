from __future__ import annotations

import json
from pathlib import Path

import click
from flask import Flask
from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from .extensions import db


def register_database_commands(app: Flask) -> None:
    @app.cli.command("migrate-sqlite-data")
    @click.option("--source", type=click.Path(path_type=Path), required=True)
    @click.option("--target", envvar="TARGET_DATABASE_URL", required=True)
    @click.option(
        "--report", "report_path", type=click.Path(path_type=Path), required=True
    )
    @click.option("--dry-run", is_flag=True, help="Validate without copying data.")
    @click.option("--allow-non-empty", is_flag=True)
    @click.option(
        "--replace-existing",
        is_flag=True,
        help="Transactionally replace application rows; requires --allow-non-empty.",
    )
    def migrate_sqlite_data_command(
        source: Path,
        target: str,
        report_path: Path,
        dry_run: bool,
        allow_non_empty: bool,
        replace_existing: bool,
    ) -> None:
        """Copy an upgraded coaching SQLite database to upgraded PostgreSQL."""
        from .sqlite_postgres_migration import MigrationError, migrate

        def progress(event: dict[str, object]) -> None:
            click.echo(json.dumps(event, sort_keys=True))

        try:
            result = migrate(
                source=source,
                target=target,
                report_path=report_path,
                metadata=db.metadata,
                dry_run=dry_run,
                allow_non_empty=allow_non_empty,
                replace_existing=replace_existing,
                progress=progress,
            )
        except (MigrationError, OSError, SQLAlchemyError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(
            json.dumps(
                {
                    "event": "report_written",
                    "status": result["status"],
                    "path": str(report_path),
                },
                sort_keys=True,
            )
        )

    @app.cli.command("seed-programming")
    def seed_programming_command() -> None:
        """Create the built-in exercises and day templates idempotently."""
        from .seed_programming_engine import seed_programming_engine

        seed_programming_engine()
        click.echo("Programming seed complete.")

    @app.cli.command("seed-exercise-catalogue")
    @click.option(
        "--verify-only",
        is_flag=True,
        help="Report counts without writing to the database.",
    )
    def seed_exercise_catalogue_command(verify_only: bool) -> None:
        """Add the reviewed catalogue without changing coach-maintained rows."""
        from .models.exercise_library import Exercise
        from .services.exercise_knowledge_import import (
            DEFAULT_DATA_PATH,
            import_exercise_knowledge_file,
        )

        before = Exercise.query.count()
        catalogue_records = len(
            json.loads(DEFAULT_DATA_PATH.read_text(encoding="utf-8"))["exercises"]
        )
        result = None if verify_only else import_exercise_knowledge_file(DEFAULT_DATA_PATH)
        after = Exercise.query.count()
        click.echo(
            json.dumps(
                {
                    "before": before,
                    "after": after,
                    "catalogue_records": catalogue_records,
                    "changes": result.as_dict() if result is not None else None,
                    "mode": "verify" if verify_only else "seed",
                },
                sort_keys=True,
            )
        )

    @app.cli.command("verify-schema")
    def verify_schema_command() -> None:
        """Check that database tables and columns match coaching metadata."""
        inspector = inspect(db.engine)
        actual_tables = set(inspector.get_table_names())
        expected_tables = set(db.metadata.tables)
        problems: list[str] = []

        missing_tables = sorted(expected_tables - actual_tables)
        if missing_tables:
            problems.append(f"missing tables: {', '.join(missing_tables)}")

        for table_name in sorted(expected_tables & actual_tables):
            expected_columns = set(db.metadata.tables[table_name].columns.keys())
            actual_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            missing_columns = sorted(expected_columns - actual_columns)
            if missing_columns:
                problems.append(
                    f"{table_name} missing columns: {', '.join(missing_columns)}"
                )

        if problems:
            raise click.ClickException(
                "Schema verification failed; " + "; ".join(problems)
            )

        click.echo(f"Schema verified: {len(expected_tables)} coaching tables.")

    @app.cli.command("verify-production-db")
    def verify_production_db_command() -> None:
        """Safely verify the private portal's PostgreSQL schema and catalogue count."""
        dialect = db.engine.dialect.name
        if dialect != "postgresql":
            raise click.ClickException(
                f"Production database verification requires PostgreSQL; found {dialect}."
            )
        inspector = inspect(db.engine)
        tables = set(inspector.get_table_names())
        required = {"users", "exercises"}
        missing = sorted(required - tables)
        if missing:
            raise click.ClickException(
                "Production database verification failed; missing tables: "
                + ", ".join(missing)
            )
        exercise_count = db.session.execute(
            db.select(db.func.count()).select_from(db.metadata.tables["exercises"])
        ).scalar_one()
        click.echo(
            f"Production database verified: driver={dialect}; "
            f"users_table=yes; exercises_table=yes; exercises={exercise_count}."
        )
