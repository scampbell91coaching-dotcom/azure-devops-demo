from __future__ import annotations

import click
from flask import Flask
from sqlalchemy import inspect

from .extensions import db


def register_database_commands(app: Flask) -> None:
    @app.cli.command("seed-programming")
    def seed_programming_command() -> None:
        """Create the built-in exercises and day templates idempotently."""
        from .seed_programming_engine import seed_programming_engine

        seed_programming_engine()
        click.echo("Programming seed complete.")

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
