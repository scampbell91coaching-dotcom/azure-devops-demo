#!/usr/bin/env python3
"""Read-only PostgreSQL restore verification with sanitised JSON evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


CONFIRMATION = "I_CONFIRM_THIS_IS_A_DISPOSABLE_RESTORE"
DEFAULT_TABLES = ("athletes", "users", "training_sessions", "training_session_logs", "meal_plan_templates", "meal_plan_assignments")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def safe_target(database_url: str, source_host: str, confirmation: str) -> tuple[str, str]:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.path.strip("/"):
        raise ValueError("RESTORE_DATABASE_URL must identify a PostgreSQL database")
    if confirmation != CONFIRMATION:
        raise ValueError(f"--confirm must equal {CONFIRMATION}")
    if parsed.hostname.casefold() == source_host.casefold():
        raise ValueError("restore target host must differ from the declared source host")
    target_fingerprint = hashlib.sha256(f"{parsed.hostname}/{parsed.path.strip('/')}".encode()).hexdigest()[:12]
    return parsed.hostname, target_fingerprint


def scalar(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return None if row is None else row[0]


def run_checks(cursor: Any, expected_head: str, critical_tables: tuple[str, ...]) -> list[Check]:
    checks: list[Check] = []
    read_only = scalar(cursor, "SHOW transaction_read_only")
    checks.append(Check("read_only_transaction", read_only == "on", f"value={read_only!r}"))

    head_rows = scalar(cursor, "SELECT count(*) FROM alembic_version")
    checks.append(Check("single_alembic_head", head_rows == 1, f"rows={head_rows}"))
    actual_head = scalar(cursor, "SELECT version_num FROM alembic_version") if head_rows == 1 else None
    checks.append(Check("expected_alembic_head", actual_head == expected_head, f"actual={actual_head!r}, expected={expected_head!r}"))

    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=current_schema() AND table_name = ANY(%s)",
        (list(critical_tables),),
    )
    existing = {row[0] for row in cursor.fetchall()}
    missing = sorted(set(critical_tables) - existing)
    checks.append(Check("critical_tables_present", not missing, f"missing={missing}"))

    unvalidated = scalar(cursor, """
        SELECT count(*) FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname=current_schema() AND c.contype IN ('c','f') AND NOT c.convalidated
    """)
    checks.append(Check("constraints_validated", unvalidated == 0, f"unvalidated={unvalidated}"))
    return checks


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-host", required=True, help="source hostname, used only as a safety comparison")
    parser.add_argument("--expected-head", required=True, help="reviewed Alembic head from the release being tested")
    parser.add_argument("--rehearsal-id", required=True, help="non-sensitive change/exercise identifier")
    parser.add_argument("--confirm", required=True, help="explicit disposable-restore acknowledgement")
    parser.add_argument("--critical-table", action="append", dest="critical_tables")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    database_url = os.environ.get("RESTORE_DATABASE_URL", "")
    try:
        _host, fingerprint = safe_target(database_url, args.source_host, args.confirm)
    except ValueError as exc:
        print(f"restore-verify: {exc}", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print("restore-verify: psycopg is required", file=sys.stderr)
        return 2

    checks: list[Check]
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '30s'")
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                checks = run_checks(cursor, args.expected_head, tuple(args.critical_tables or DEFAULT_TABLES))
            connection.rollback()
    except Exception as exc:  # sanitized: never emit URI or server-provided detail
        print(f"restore-verify: database check failed ({type(exc).__name__})", file=sys.stderr)
        return 2

    evidence = {
        "schema": "traditional-strength.restore-verification.v1",
        "rehearsal_id": args.rehearsal_id,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_fingerprint": fingerprint,
        "checks": [asdict(check) for check in checks],
        "passed": all(check.ok for check in checks),
    }
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
