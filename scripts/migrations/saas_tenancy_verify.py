#!/usr/bin/env python3
"""Read-only verification gates for the multi-tenant schema rollout.

This deliberately does not import application models: it verifies the deployed
PostgreSQL schema and data, including mixed-version deployments.  Every
connection is placed in a read-only transaction before checks are executed.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Iterable


EXPECTED_HEAD = "0022_support_admin_foundation"
CONTROL_TABLES = (
    "organisations",
    "organisation_memberships",
    "coach_athlete_ownerships",
    "organisation_invitations",
    "subscription_accounts",
    "billing_webhook_events",
    "support_principals",
    "support_capability_grants",
    "support_access_events",
    "support_delegations",
)
REMOVED_TABLES = (
    "organizations",
    "organization_memberships",
    "organization_athletes",
    "organization_invitations",
    "organization_onboarding",
    "memberships",
    "membership_invitations",
    "membership_invitation_audit",
    "organisation_athletes",
)
PHASES = ("expand", "backfill", "constrain")


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def _scalar(cursor: Any, sql: str, params: Iterable[Any] = ()) -> Any:
    cursor.execute(sql, tuple(params))
    row = cursor.fetchone()
    return None if row is None else row[0]


def _ident(value: str) -> str:
    """Quote a catalog-derived PostgreSQL identifier."""
    return '"' + value.replace('"', '""') + '"'


def run_checks(cursor: Any, phase: str, expected_head: str = EXPECTED_HEAD) -> list[CheckResult]:
    results: list[CheckResult] = []
    heads = _scalar(cursor, "SELECT count(*) FROM alembic_version")
    results.append(CheckResult("single_alembic_head", heads == 1, f"rows={heads}"))
    actual = _scalar(cursor, "SELECT version_num FROM alembic_version") if heads == 1 else None
    results.append(CheckResult("expected_alembic_head", actual == expected_head, f"actual={actual!r}"))

    existing = set()
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = ANY(%s)",
        (list(CONTROL_TABLES),),
    )
    existing = {row[0] for row in cursor.fetchall()}
    missing = sorted(set(CONTROL_TABLES) - existing)
    results.append(CheckResult("control_tables_exist", not missing, f"missing={missing}"))
    cursor.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = current_schema() AND table_name = ANY(%s)",
        (list(REMOVED_TABLES),),
    )
    stale = sorted(row[0] for row in cursor.fetchall())
    results.append(CheckResult("removed_schema_families_absent", not stale, f"present={stale}"))
    if missing:
        return results

    cursor.execute(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND column_name = 'organisation_id' "
        "ORDER BY table_name"
    )
    tenant_tables = [row[0] for row in cursor.fetchall()]
    results.append(CheckResult("tenant_columns_present", bool(tenant_tables), f"tables={tenant_tables}"))

    if phase == "expand":
        return results

    for table in tenant_tables:
        quoted = _ident(table)
        nulls = _scalar(cursor, f"SELECT count(*) FROM {quoted} WHERE organisation_id IS NULL")
        orphans = _scalar(
            cursor,
            f"SELECT count(*) FROM {quoted} t LEFT JOIN organisations o ON o.id=t.organisation_id "
            "WHERE t.organisation_id IS NOT NULL AND o.id IS NULL",
        )
        results.append(CheckResult(f"{table}.ownership_complete", nulls == 0 and orphans == 0, f"null={nulls}, orphan={orphans}"))

    # Discover every FK edge whose two tables materialize organisation_id.
    cursor.execute("""
        SELECT child.relname, parent.relname, ca.attname, pa.attname
        FROM pg_constraint fk
        JOIN pg_class child ON child.oid=fk.conrelid
        JOIN pg_class parent ON parent.oid=fk.confrelid
        JOIN pg_namespace ns ON ns.oid=child.relnamespace AND ns.nspname=current_schema()
        JOIN LATERAL unnest(fk.conkey, fk.confkey) keys(child_attnum,parent_attnum) ON true
        JOIN pg_attribute ca ON ca.attrelid=child.oid AND ca.attnum=keys.child_attnum
        JOIN pg_attribute pa ON pa.attrelid=parent.oid AND pa.attnum=keys.parent_attnum
        WHERE fk.contype='f'
          AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=child.oid AND a.attname='organisation_id' AND NOT a.attisdropped)
          AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=parent.oid AND a.attname='organisation_id' AND NOT a.attisdropped)
          AND ca.attname <> 'organisation_id'
        ORDER BY child.relname, parent.relname, ca.attname
    """)
    for child, parent, child_key, parent_key in cursor.fetchall():
        mismatches = _scalar(
            cursor,
            f"SELECT count(*) FROM {_ident(child)} c JOIN {_ident(parent)} p "
            f"ON p.{_ident(parent_key)}=c.{_ident(child_key)} "
            "WHERE c.organisation_id IS DISTINCT FROM p.organisation_id",
        )
        results.append(CheckResult(f"{child}.{child_key}_tenant_match", mismatches == 0, f"mismatches={mismatches}"))

    if phase == "backfill":
        return results

    unvalidated = _scalar(cursor, """
        SELECT count(*) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname=current_schema() AND c.contype IN ('f','c') AND NOT c.convalidated
    """)
    results.append(CheckResult("constraints_validated", unvalidated == 0, f"unvalidated={unvalidated}"))
    nullable = _scalar(cursor, """
        SELECT count(*) FROM information_schema.columns
        WHERE table_schema=current_schema() AND column_name='organisation_id'
          AND table_name <> 'organisations' AND is_nullable='YES'
    """)
    results.append(CheckResult("tenant_keys_not_null", nullable == 0, f"nullable={nullable}"))
    missing_indexes = _scalar(cursor, """
        SELECT count(*) FROM information_schema.columns col
        WHERE col.table_schema=current_schema() AND col.column_name='organisation_id'
          AND col.table_name <> 'organisations' AND NOT EXISTS (
            SELECT 1 FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
            JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=(i.indkey::int2[])[0]
            WHERE n.nspname=current_schema() AND t.relname=col.table_name
              AND i.indisvalid AND a.attname='organisation_id')
    """)
    results.append(CheckResult("tenant_leading_indexes", missing_indexes == 0, f"missing={missing_indexes}"))
    missing_composite_fks = _scalar(cursor, """
        WITH tenant_edges AS (
          SELECT DISTINCT fk.conrelid child_oid, fk.confrelid parent_oid
          FROM pg_constraint fk
          WHERE fk.contype='f'
            AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=fk.conrelid AND a.attname='organisation_id' AND NOT a.attisdropped)
            AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=fk.confrelid AND a.attname='organisation_id' AND NOT a.attisdropped)
        )
        SELECT count(*) FROM tenant_edges e WHERE NOT EXISTS (
          SELECT 1 FROM pg_constraint composite
          WHERE composite.contype='f' AND composite.conrelid=e.child_oid
            AND composite.confrelid=e.parent_oid AND composite.convalidated
            AND EXISTS (SELECT 1 FROM unnest(composite.conkey) key(attnum)
                        JOIN pg_attribute a ON a.attrelid=e.child_oid AND a.attnum=key.attnum
                        WHERE a.attname='organisation_id'))
    """)
    results.append(CheckResult("tenant_edges_have_composite_fks", missing_composite_fks == 0, f"missing={missing_composite_fks}"))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--expected-head", default=EXPECTED_HEAD)
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    import psycopg

    with psycopg.connect(args.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
            results = run_checks(cursor, args.phase, args.expected_head)
            connection.rollback()
    print(json.dumps({"phase": args.phase, "ok": all(r.ok for r in results), "checks": [asdict(r) for r in results]}, indent=2))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
