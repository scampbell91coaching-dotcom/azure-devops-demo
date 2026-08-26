#!/usr/bin/env python3
"""Read-only PostgreSQL restore verification with sanitised JSON evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit


CONFIRMATION = "I_CONFIRM_THIS_IS_A_DISPOSABLE_RESTORE"
DEFAULT_TABLES = (
    "athletes", "users", "training_sessions", "training_session_logs",
    "meal_plan_templates", "meal_plan_assignments", "organisations",
    "organisation_memberships", "coach_athlete_ownerships", "pdf_meal_plans",
)
PRODUCTION_RE = re.compile(r"(^|[.\-_/])(prod(uction)?|live)([.\-_/]|$)", re.IGNORECASE)
DISPOSABLE_RE = re.compile(r"(^|[.\-_/])(restore|drill|disposable|sandbox)([.\-_/]|$)", re.IGNORECASE)


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def target_identity(database_url: str) -> tuple[str, str]:
    parsed = urlsplit(database_url)
    database = parsed.path.strip("/")
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not database:
        raise ValueError("RESTORE_DATABASE_URL must identify a PostgreSQL database")
    return parsed.hostname, database


def safe_target(database_url: str, source_host: str, confirmation: str) -> tuple[str, str]:
    host, database = target_identity(database_url)
    identity = f"{host}/{database}"
    if confirmation != CONFIRMATION:
        raise ValueError(f"--confirm must equal {CONFIRMATION}")
    if host.casefold().rstrip(".") == source_host.casefold().rstrip("."):
        raise ValueError("restore target host must differ from the declared source host")
    if PRODUCTION_RE.search(identity):
        raise ValueError("restore target resembles production")
    if not DISPOSABLE_RE.search(identity):
        raise ValueError("restore target must be explicitly named restore, drill, disposable, or sandbox")
    fingerprint = hashlib.sha256(identity.casefold().encode()).hexdigest()[:12]
    return host, fingerprint


def scalar(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return None if row is None else row[0]


def _check_count(cursor: Any, table: str, minimum: int) -> Check:
    # Identifiers are accepted only from the fixed defaults or strictly parsed CLI input.
    count = scalar(cursor, f'SELECT count(*) FROM "{table}"')
    return Check(f"critical_table_count:{table}", count >= minimum, f"count={count}, minimum={minimum}")


def verify_pdf_content(cursor: Any) -> tuple[int, int]:
    """Return aggregate metadata and SHA-256 mismatch counts without exposing rows."""
    cursor.execute("SELECT pdf_bytes, content_sha256, content_length FROM pdf_meal_plans")
    metadata_mismatches = 0
    hash_mismatches = 0
    while rows := cursor.fetchmany(100):
        for pdf_bytes, stored_sha256, stored_length in rows:
            payload = bytes(pdf_bytes) if pdf_bytes is not None else b""
            actual_length = len(payload)
            actual_sha256 = hashlib.sha256(payload).hexdigest()
            valid_stored_hash = isinstance(stored_sha256, str) and re.fullmatch(
                r"[0-9a-f]{64}", stored_sha256
            ) is not None
            if stored_length != actual_length or actual_length <= 0 or not valid_stored_hash:
                metadata_mismatches += 1
            if not valid_stored_hash or actual_sha256 != stored_sha256:
                hash_mismatches += 1
    return metadata_mismatches, hash_mismatches


def run_checks(cursor: Any, expected_head: str, minimum_counts: dict[str, int]) -> list[Check]:
    checks: list[Check] = []
    read_only = scalar(cursor, "SHOW transaction_read_only")
    checks.append(Check("read_only_transaction", read_only == "on", f"value={read_only!r}"))

    head_rows = scalar(cursor, "SELECT count(*) FROM alembic_version")
    checks.append(Check("single_alembic_head", head_rows == 1, f"rows={head_rows}"))
    actual_head = scalar(cursor, "SELECT version_num FROM alembic_version") if head_rows == 1 else None
    checks.append(Check("expected_alembic_head", actual_head == expected_head, f"actual={actual_head!r}, expected={expected_head!r}"))

    tables = tuple(minimum_counts)
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=current_schema() AND table_name = ANY(%s)", (list(tables),),
    )
    existing = {row[0] for row in cursor.fetchall()}
    missing = sorted(set(tables) - existing)
    checks.append(Check("critical_tables_present", not missing, f"missing={missing}"))
    for table in tables:
        if table in existing:
            checks.append(_check_count(cursor, table, minimum_counts[table]))

    unvalidated = scalar(cursor, """
        SELECT count(*) FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname=current_schema() AND c.contype IN ('c','f','u','p') AND NOT c.convalidated
    """)
    checks.append(Check("constraints_validated", unvalidated == 0, f"unvalidated={unvalidated}"))
    invalid_indexes = scalar(cursor, """
        SELECT count(*) FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname=current_schema() AND (NOT i.indisvalid OR NOT i.indisready)
    """)
    checks.append(Check("indexes_valid_and_ready", invalid_indexes == 0, f"invalid_or_unready={invalid_indexes}"))

    tenant_mismatches = scalar(cursor, """
        SELECT count(*) FROM coach_athlete_ownerships o
        JOIN organisation_memberships m ON m.id=o.coach_membership_id
        WHERE o.organisation_id <> m.organisation_id
    """) if {"coach_athlete_ownerships", "organisation_memberships"} <= existing else None
    checks.append(Check("tenant_ownership_consistent", tenant_mismatches == 0, f"mismatches={tenant_mismatches}"))

    pdf_mismatches = scalar(cursor, """
        SELECT count(*) FROM pdf_meal_plans p
        WHERE NOT EXISTS (
          SELECT 1 FROM coach_athlete_ownerships o
          JOIN organisation_memberships m
            ON m.id=o.coach_membership_id AND m.organisation_id=o.organisation_id
          WHERE o.organisation_id=p.organisation_id AND o.athlete_id=p.athlete_id
            AND m.user_id=p.coach_id
        )
    """) if {"pdf_meal_plans", "coach_athlete_ownerships", "organisation_memberships"} <= existing else None
    checks.append(Check("pdf_tenant_ownership", pdf_mismatches == 0, f"mismatches={pdf_mismatches}"))

    hidden_sequences = scalar(cursor, """
        SELECT count(*) FROM pg_sequences s
        JOIN pg_class seq ON seq.relname=s.sequencename
        JOIN pg_namespace ns ON ns.oid=seq.relnamespace AND ns.nspname=s.schemaname
        JOIN pg_depend d ON d.objid=seq.oid AND d.deptype IN ('a','i')
        WHERE s.schemaname=current_schema() AND s.last_value IS NULL
    """)
    checks.append(Check("sequence_values_visible", hidden_sequences == 0, f"not_visible={hidden_sequences}"))
    sequence_behind = scalar(cursor, """
        SELECT count(*) FROM pg_sequences s
        JOIN pg_class seq ON seq.relname=s.sequencename
        JOIN pg_namespace ns ON ns.oid=seq.relnamespace AND ns.nspname=s.schemaname
        JOIN pg_depend d ON d.objid=seq.oid AND d.deptype IN ('a','i')
        JOIN pg_class tab ON tab.oid=d.refobjid
        JOIN pg_attribute a ON a.attrelid=tab.oid AND a.attnum=d.refobjsubid
        WHERE s.schemaname=current_schema()
          AND s.last_value IS NOT NULL
          AND s.last_value < COALESCE((xpath('/row/max/text()', query_to_xml(
            format('SELECT max(%I) AS max FROM %I.%I', a.attname, s.schemaname, tab.relname),
            false, true, '')))[1]::text::bigint, 0)
    """)
    checks.append(Check("sequences_not_behind", sequence_behind == 0, f"behind={sequence_behind}"))

    if "pdf_meal_plans" in existing:
        metadata_mismatches, hash_mismatches = verify_pdf_content(cursor)
        checks.append(Check(
            "pdf_metadata", metadata_mismatches == 0,
            f"status={'passed' if metadata_mismatches == 0 else 'failed'}, mismatch_count={metadata_mismatches}",
        ))
        checks.append(Check(
            "pdf_content_sha256", hash_mismatches == 0,
            f"status={'passed' if hash_mismatches == 0 else 'failed'}, mismatch_count={hash_mismatches}",
        ))
    else:
        missing_detail = "status=failed, mismatch_count=unavailable"
        checks.append(Check("pdf_metadata", False, missing_detail))
        checks.append(Check("pdf_content_sha256", False, missing_detail))
    return checks


def parse_minimum_counts(values: list[str] | None) -> dict[str, int]:
    result = {table: 0 for table in DEFAULT_TABLES}
    for value in values or []:
        try:
            table, raw = value.split("=", 1)
            if not re.fullmatch(r"[a-z][a-z0-9_]*", table) or int(raw) < 0:
                raise ValueError
            result[table] = int(raw)
        except ValueError as exc:
            raise ValueError(f"invalid --minimum-count {value!r}; expected table=nonnegative_integer") from exc
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-host", required=True, help="production source hostname; comparison only")
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--rehearsal-id", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--minimum-count", action="append", help="repeatable table=minimum expectation")
    parser.add_argument("--output", help="write JSON evidence atomically; stdout if omitted")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _host, fingerprint = safe_target(os.environ.get("RESTORE_DATABASE_URL", ""), args.source_host, args.confirm)
        minimum_counts = parse_minimum_counts(args.minimum_count)
    except ValueError as exc:
        print(f"restore-verify: {exc}", file=sys.stderr)
        return 2
    try:
        import psycopg
    except ImportError:
        print("restore-verify: psycopg is required", file=sys.stderr)
        return 2
    try:
        with psycopg.connect(os.environ["RESTORE_DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '30s'")
                cursor.execute("SET LOCAL lock_timeout = '5s'")
                checks = run_checks(cursor, args.expected_head, minimum_counts)
            connection.rollback()
    except Exception as exc:
        print(f"restore-verify: database check failed ({type(exc).__name__})", file=sys.stderr)
        return 2
    evidence = {
        "schema": "traditional-strength.restore-verification.v2",
        "rehearsal_id": args.rehearsal_id,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_fingerprint": fingerprint,
        "checks": [asdict(check) for check in checks],
        "passed": all(check.ok for check in checks),
    }
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output:
        temporary = f"{args.output}.tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            stream.write(rendered)
        os.replace(temporary, args.output)
    else:
        print(rendered, end="")
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
