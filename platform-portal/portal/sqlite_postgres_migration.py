from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Engine,
    MetaData,
    Table,
    and_,
    create_engine,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.sql.ddl import sort_tables_and_constraints


class MigrationError(RuntimeError):
    """A validation or verification failure safe to show to an operator."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def source_engine(path: Path) -> Engine:
    """Open SQLite read-only so this tool cannot rewrite the source file."""

    absolute = path.resolve()
    return create_engine(
        "sqlite+pysqlite://",
        creator=lambda: sqlite3.connect(
            f"file:{absolute}?mode=ro", uri=True, check_same_thread=False
        ),
        poolclass=NullPool,
    )


def postgres_engine(target: str) -> Engine:
    try:
        url = make_url(target)
    except Exception as exc:
        raise MigrationError(f"Invalid target database URL: {exc}") from exc
    if url.get_backend_name() not in {"postgres", "postgresql"}:
        raise MigrationError("Target database URL must use PostgreSQL")
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(url, pool_pre_ping=True)


def safe_target(target: str) -> dict[str, str | None]:
    try:
        url: URL = make_url(target)
    except Exception as exc:
        raise MigrationError(f"Invalid target database URL: {exc}") from exc
    return {"host": url.host, "database": url.database}


def table_order(metadata: MetaData) -> list[Table]:
    """Use SQLAlchemy's FK dependency sorter, failing on cycles."""

    sorted_items = list(sort_tables_and_constraints(metadata.tables.values()))
    tables = [table for table, _constraints in sorted_items if table is not None]
    deferred = [
        constraint
        for table, constraints in sorted_items
        if table is None
        for constraint in constraints
    ]
    if deferred:
        raise MigrationError("Cyclic foreign-key dependencies are unsupported")
    return tables


def validate_schema(engine: Engine, metadata: MetaData, *, label: str) -> None:
    inspector = inspect(engine)
    actual = set(inspector.get_table_names())
    expected = set(metadata.tables)
    missing = sorted(expected - actual)
    problems = [f"missing tables: {', '.join(missing)}"] if missing else []
    for name in sorted(expected & actual):
        columns = {item["name"] for item in inspector.get_columns(name)}
        expected_columns = {column.name for column in metadata.tables[name].columns}
        missing_columns = sorted(expected_columns - columns)
        if missing_columns:
            problems.append(f"{name} missing columns: {', '.join(missing_columns)}")
    if problems:
        raise MigrationError(f"{label} schema is unsupported; " + "; ".join(problems))


def validate_additional_tables(
    engine: Engine, metadata: MetaData, *, label: str
) -> None:
    actual = set(inspect(engine).get_table_names())
    allowed_metadata = {"alembic_version"}
    unsupported = sorted(actual - set(metadata.tables) - allowed_metadata)
    if unsupported:
        raise MigrationError(
            f"{label} contains unsupported tables outside application metadata: "
            + ", ".join(unsupported)
        )


def counts(connection: Any, tables: Iterable[Table]) -> dict[str, int]:
    return {
        table.name: int(
            connection.execute(select(func.count()).select_from(table)).scalar_one()
        )
        for table in tables
    }


def verify_constraints(connection: Any, tables: list[Table]) -> dict[str, Any]:
    orphan_checks: dict[str, int] = {}
    unique_checks: dict[str, int] = {}
    for table in tables:
        for fk in table.foreign_key_constraints:
            pairs = list(fk.elements)
            parent = pairs[0].column.table
            parent_source = (
                parent.alias(f"{parent.name}_parent")
                if parent is table
                else parent
            )
            parent_columns = [
                parent_source.c[pair.column.name]
                for pair in pairs
            ]
            join = table.join(
                parent_source,
                and_(
                    *(
                        pair.parent == parent_column
                        for pair, parent_column in zip(
                            pairs, parent_columns, strict=True
                        )
                    )
                ),
                isouter=True,
            )
            populated = [pair.parent.is_not(None) for pair in pairs]
            query = (
                select(func.count())
                .select_from(join)
                .where(*populated, parent_columns[0].is_(None))
            )
            key = f"{table.name}->{parent.name}"
            orphan_checks[key] = int(connection.execute(query).scalar_one())

        unique_sets: set[tuple[str, ...]] = set()
        for constraint in table.constraints:
            if constraint.__class__.__name__ == "UniqueConstraint":
                unique_sets.add(tuple(column.name for column in constraint.columns))
        for index in table.indexes:
            if index.unique:
                unique_sets.add(tuple(column.name for column in index.columns))
        for names in sorted(unique_sets):
            columns = [table.c[name] for name in names]
            duplicates = (
                select(func.count())
                .select_from(table)
                .where(*(column.is_not(None) for column in columns))
                .group_by(*columns)
                .having(func.count() > 1)
                .subquery()
            )
            key = f"{table.name}({','.join(names)})"
            unique_checks[key] = int(
                connection.execute(
                    select(func.count()).select_from(duplicates)
                ).scalar_one()
            )
    return {
        "foreign_keys": orphan_checks,
        "unique_constraints": unique_checks,
        "foreign_keys_valid": not any(orphan_checks.values()),
        "unique_constraints_valid": not any(unique_checks.values()),
    }


def reset_sequences(connection: Any, tables: list[Table]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for table in tables:
        integer_pks = []
        for column in table.primary_key.columns:
            try:
                if column.type.python_type is int:
                    integer_pks.append(column)
            except NotImplementedError:
                continue
        if len(integer_pks) != 1:
            continue
        column = integer_pks[0]
        sequence = connection.execute(
            select(func.pg_get_serial_sequence(table.name, column.name))
        ).scalar_one_or_none()
        maximum = connection.execute(select(func.max(column))).scalar_one()
        if sequence:
            if maximum is None:
                connection.execute(
                    text("SELECT setval(CAST(:sequence AS regclass), 1, false)"),
                    {"sequence": sequence},
                )
            else:
                connection.execute(
                    text("SELECT setval(CAST(:sequence AS regclass), :value, true)"),
                    {"sequence": sequence, "value": maximum},
                )
            sequence_value = connection.execute(
                text("SELECT pg_sequence_last_value(CAST(:sequence AS regclass))"),
                {"sequence": sequence},
            ).scalar_one()
        else:
            sequence_value = None
        results[table.name] = {
            "column": column.name,
            "maximum_id": maximum,
            "sequence": sequence,
            "sequence_value": sequence_value,
            "aligned": bool(sequence)
            and (
                sequence_value == maximum
                if maximum is not None
                else sequence_value in (None, 1)
            ),
        }
    return results


def representative_reads(connection: Any, metadata: MetaData) -> dict[str, bool]:
    names = {
        "athletes": "athletes",
        "check_ins": "weekly_checkins",
        "training_blocks": "training_blocks",
        "weeks": "training_weeks",
        "sessions": "training_sessions",
        "prescriptions": "exercise_prescriptions",
        "exercises": "exercises",
        "nutrition_check_ins": "nutrition_checkins",
    }
    result: dict[str, bool] = {}
    for label, name in names.items():
        connection.execute(select(metadata.tables[name]).limit(1)).first()
        result[label] = True
    return result


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def migrate(
    *,
    source: Path,
    target: str,
    report_path: Path,
    metadata: MetaData,
    dry_run: bool = False,
    allow_non_empty: bool = False,
    replace_existing: bool = False,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    emit = progress or (lambda _event: None)
    report: dict[str, Any] = {
        "source_path": str(source.resolve()),
        "target": None,
        "started_at": utc_now(),
        "completed_at": None,
        "source_table_counts": {},
        "target_table_counts_before": {},
        "inserted_row_counts": {},
        "skipped_table_counts": {},
        "target_table_counts_after": {},
        "sequence_reset_results": {},
        "verification_results": {},
        "errors": [],
        "status": "running",
        "dry_run": dry_run,
    }
    source_db: Engine | None = None
    target_db: Engine | None = None
    try:
        if not source.is_file():
            raise MigrationError(f"Source SQLite file does not exist: {source}")
        if source.name == "public-leads.db":
            raise MigrationError(
                "public-leads.db is explicitly outside migration scope"
            )
        report["target"] = safe_target(target)
        target_db = postgres_engine(target)
        source_db = source_engine(source)
        tables = table_order(metadata)
        validate_schema(source_db, metadata, label="Source")
        validate_additional_tables(source_db, metadata, label="Source")
        validate_schema(target_db, metadata, label="Target")
        validate_additional_tables(target_db, metadata, label="Target")
        target_tables = set(inspect(target_db).get_table_names())
        if "alembic_version" not in target_tables:
            raise MigrationError(
                "Target schema is not Alembic-upgraded (alembic_version missing)"
            )

        with target_db.connect() as target_connection:
            if not target_connection.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar_one_or_none():
                raise MigrationError("Target Alembic revision is missing")

        with (
            source_db.connect() as source_connection,
            target_db.connect() as target_connection,
        ):
            report["source_table_counts"] = counts(source_connection, tables)
            report["target_table_counts_before"] = counts(target_connection, tables)
        non_empty = {k: v for k, v in report["target_table_counts_before"].items() if v}
        if non_empty and not allow_non_empty:
            raise MigrationError(
                "Target contains application data; pass --allow-non-empty explicitly"
            )
        if replace_existing and not allow_non_empty:
            raise MigrationError("--replace-existing requires --allow-non-empty")
        if non_empty and allow_non_empty and not replace_existing:
            raise MigrationError(
                "Non-empty migration requires --replace-existing to avoid duplicate or mixed data"
            )

        report["skipped_table_counts"] = {table.name: 0 for table in tables}
        with source_db.connect() as source_connection:
            preflight = verify_constraints(source_connection, tables)
        report["verification_results"]["source"] = preflight
        if (
            not preflight["foreign_keys_valid"]
            or not preflight["unique_constraints_valid"]
        ):
            raise MigrationError("Source constraint verification failed")
        if dry_run:
            report["inserted_row_counts"] = {table.name: 0 for table in tables}
            report["target_table_counts_after"] = report["target_table_counts_before"]
            report["verification_results"]["schema"] = "verified"
            report["status"] = "dry-run-complete"
            emit({"event": "dry_run_complete", "tables": len(tables)})
        else:
            with (
                source_db.connect() as source_connection,
                target_db.begin() as target_connection,
            ):
                if replace_existing:
                    for table in reversed(tables):
                        target_connection.execute(table.delete())
                    emit({"event": "target_cleared", "tables": len(tables)})
                for table in tables:
                    rows = [
                        dict(row)
                        for row in source_connection.execute(select(table)).mappings()
                    ]
                    if rows:
                        target_connection.execute(table.insert(), rows)
                    report["inserted_row_counts"][table.name] = len(rows)
                    emit(
                        {
                            "event": "table_copied",
                            "table": table.name,
                            "rows": len(rows),
                        }
                    )
                report["sequence_reset_results"] = reset_sequences(
                    target_connection, tables
                )
                after = counts(target_connection, tables)
                report["target_table_counts_after"] = after
                expected = report["source_table_counts"]
                count_matches = {
                    name: after[name] == expected[name] for name in expected
                }
                checks = verify_constraints(target_connection, tables)
                checks["row_counts"] = count_matches
                checks["row_counts_valid"] = all(count_matches.values())
                checks["representative_reads"] = representative_reads(
                    target_connection, metadata
                )
                checks["schema"] = "verified"
                report["verification_results"]["target"] = checks
                if not all(
                    (
                        checks["row_counts_valid"],
                        checks["foreign_keys_valid"],
                        checks["unique_constraints_valid"],
                    )
                ):
                    raise MigrationError(
                        "Target verification failed; transaction rolled back"
                    )
            report["status"] = "completed"
            emit({"event": "migration_complete", "tables": len(tables)})
    except Exception as exc:
        report["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        report["status"] = "failed"
        emit({"event": "migration_failed", "error": str(exc)})
        raise
    finally:
        report["completed_at"] = utc_now()
        write_report(report_path, report)
        if source_db is not None:
            source_db.dispose()
        if target_db is not None:
            target_db.dispose()
    return report
