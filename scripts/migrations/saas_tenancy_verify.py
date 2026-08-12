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


CONTROL_TABLES = (
    "organizations",
    "organization_memberships",
    "coach_athlete_assignments",
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


def run_checks(cursor: Any, phase: str, legacy_slug: str, expected_head: str | None) -> list[CheckResult]:
    results: list[CheckResult] = []
    heads = _scalar(cursor, "SELECT count(*) FROM alembic_version")
    results.append(CheckResult("single_alembic_head", heads == 1, f"rows={heads}"))
    if expected_head:
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
    if missing:
        return results

    legacy_count = _scalar(cursor, "SELECT count(*) FROM organizations WHERE slug = %s", (legacy_slug,))
    results.append(CheckResult("one_legacy_organization", legacy_count == 1, f"count={legacy_count}"))

    cursor.execute(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND column_name = 'organization_id' "
        "ORDER BY table_name"
    )
    tenant_tables = [row[0] for row in cursor.fetchall()]
    results.append(CheckResult("tenant_columns_present", "athletes" in tenant_tables, f"tables={len(tenant_tables)}"))

    if phase == "expand":
        return results

    owner_count = _scalar(
        cursor,
        "SELECT count(*) FROM organization_memberships m "
        "JOIN organizations o ON o.id=m.organization_id "
        "WHERE o.slug=%s AND m.role='owner' AND m.status='active'",
        (legacy_slug,),
    )
    results.append(CheckResult("legacy_active_owner", owner_count >= 1, f"count={owner_count}"))
    missing_coaches = _scalar(
        cursor,
        "SELECT count(*) FROM users u WHERE u.role='coach' AND u.active "
        "AND NOT EXISTS (SELECT 1 FROM organization_memberships m JOIN organizations o ON o.id=m.organization_id "
        "WHERE m.user_id=u.id AND o.slug=%s AND m.status='active' AND m.role IN ('owner','admin','coach'))",
        (legacy_slug,),
    )
    results.append(CheckResult("legacy_coaches_have_membership", missing_coaches == 0, f"missing={missing_coaches}"))
    athlete_link_errors = _scalar(
        cursor,
        "SELECT count(*) FROM users u JOIN athletes a ON a.id=u.athlete_id "
        "LEFT JOIN organization_memberships m ON m.user_id=u.id AND m.organization_id=a.organization_id "
        "AND m.role='athlete' AND m.status='active' "
        "WHERE u.role='athlete' AND u.active AND m.id IS NULL",
    )
    results.append(CheckResult("athlete_users_have_matching_membership", athlete_link_errors == 0, f"missing={athlete_link_errors}"))

    for table in tenant_tables:
        quoted = _ident(table)
        nulls = _scalar(cursor, f"SELECT count(*) FROM {quoted} WHERE organization_id IS NULL")
        orphans = _scalar(
            cursor,
            f"SELECT count(*) FROM {quoted} t LEFT JOIN organizations o ON o.id=t.organization_id "
            "WHERE t.organization_id IS NOT NULL AND o.id IS NULL",
        )
        results.append(CheckResult(f"{table}.ownership_complete", nulls == 0 and orphans == 0, f"null={nulls}, orphan={orphans}"))

    # Discover every FK edge whose two tables materialize organization_id.
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
          AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=child.oid AND a.attname='organization_id' AND NOT a.attisdropped)
          AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=parent.oid AND a.attname='organization_id' AND NOT a.attisdropped)
          AND ca.attname <> 'organization_id'
        ORDER BY child.relname, parent.relname, ca.attname
    """)
    for child, parent, child_key, parent_key in cursor.fetchall():
        mismatches = _scalar(
            cursor,
            f"SELECT count(*) FROM {_ident(child)} c JOIN {_ident(parent)} p "
            f"ON p.{_ident(parent_key)}=c.{_ident(child_key)} "
            "WHERE c.organization_id IS DISTINCT FROM p.organization_id",
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
        WHERE table_schema=current_schema() AND column_name='organization_id'
          AND table_name <> 'organizations' AND is_nullable='YES'
    """)
    results.append(CheckResult("tenant_keys_not_null", nullable == 0, f"nullable={nullable}"))
    missing_indexes = _scalar(cursor, """
        SELECT count(*) FROM information_schema.columns col
        WHERE col.table_schema=current_schema() AND col.column_name='organization_id'
          AND col.table_name <> 'organizations' AND NOT EXISTS (
            SELECT 1 FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
            JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=(i.indkey::int2[])[0]
            WHERE n.nspname=current_schema() AND t.relname=col.table_name
              AND i.indisvalid AND a.attname='organization_id')
    """)
    results.append(CheckResult("tenant_leading_indexes", missing_indexes == 0, f"missing={missing_indexes}"))
    missing_composite_fks = _scalar(cursor, """
        WITH tenant_edges AS (
          SELECT DISTINCT fk.conrelid child_oid, fk.confrelid parent_oid
          FROM pg_constraint fk
          WHERE fk.contype='f'
            AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=fk.conrelid AND a.attname='organization_id' AND NOT a.attisdropped)
            AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid=fk.confrelid AND a.attname='organization_id' AND NOT a.attisdropped)
        )
        SELECT count(*) FROM tenant_edges e WHERE NOT EXISTS (
          SELECT 1 FROM pg_constraint composite
          WHERE composite.contype='f' AND composite.conrelid=e.child_oid
            AND composite.confrelid=e.parent_oid AND composite.convalidated
            AND EXISTS (SELECT 1 FROM unnest(composite.conkey) key(attnum)
                        JOIN pg_attribute a ON a.attrelid=e.child_oid AND a.attnum=key.attnum
                        WHERE a.attname='organization_id'))
    """)
    results.append(CheckResult("tenant_edges_have_composite_fks", missing_composite_fks == 0, f"missing={missing_composite_fks}"))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--legacy-slug", default="traditional-strength-legacy")
    parser.add_argument("--expected-head")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    import psycopg

    with psycopg.connect(args.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '30s'")
            results = run_checks(cursor, args.phase, args.legacy_slug, args.expected_head)
            connection.rollback()
    print(json.dumps({"phase": args.phase, "ok": all(r.ok for r in results), "checks": [asdict(r) for r in results]}, indent=2))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
