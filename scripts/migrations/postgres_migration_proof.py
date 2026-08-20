#!/usr/bin/env python3
"""Prove the canonical Alembic tail on an isolated PostgreSQL schema.

The database exercise is deliberately opt-in: only POSTGRES_TEST_DATABASE_URL
is consumed.  The target database is not created, stamped, or otherwise
modified outside a uniquely named schema which is removed on exit.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from itertools import pairwise
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]
PORTAL_ROOT = REPO_ROOT / "platform-portal"
EXPECTED_CHAIN = (
    "0019_meal_plan_delivery",
    "0020_organisation_ownership_domain",
    "0021_saas_billing_foundation",
    "0022_support_admin_foundation",
    "0023_organisation_invitation_delivery",
    "0024_pdf_meal_plan_delivery",
    "0025_warmup_lift_slot_target",
    "0026_programming_exposure_roles",
    "0027_tenancy_ownership_expand",
)
EXPECTED_HEAD = EXPECTED_CHAIN[-1]


def migration_graph() -> dict[str, Any]:
    config = Config(str(PORTAL_ROOT / "migrations" / "alembic.ini"))
    config.set_main_option("script_location", str(PORTAL_ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    heads = list(scripts.get_heads())
    transitions = []
    for previous, current in pairwise(EXPECTED_CHAIN):
        revision = scripts.get_revision(current)
        transitions.append({
            "from": previous,
            "to": current,
            "declared_parent": revision.down_revision if revision else None,
            "ok": revision is not None and revision.down_revision == previous,
        })
    return {
        "expected_chain": list(EXPECTED_CHAIN),
        "heads": heads,
        "single_expected_head": heads == [EXPECTED_HEAD],
        "transitions": transitions,
        "ok": heads == [EXPECTED_HEAD] and all(item["ok"] for item in transitions),
    }


def _postgres_url(value: str) -> str:
    url = make_url(value)
    if url.get_backend_name() != "postgresql":
        raise ValueError("POSTGRES_TEST_DATABASE_URL must use PostgreSQL")
    return value


def _run(command: list[str], env: dict[str, str]) -> str:
    completed = subprocess.run(
        command, cwd=PORTAL_ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stdout}"
        )
    return completed.stdout.strip()


def database_proof(database_url: str) -> dict[str, Any]:
    database_url = _postgres_url(database_url)
    schema = f"pl_migration_proof_{secrets.token_hex(8)}"
    quoted_schema = '"' + schema.replace('"', '""') + '"'
    engine = create_engine(database_url, isolation_level="AUTOCOMMIT")
    evidence: dict[str, Any] = {"schema": schema, "upgrades": [], "cleaned_up": False}
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": database_url,
        "PGOPTIONS": f"-c search_path={schema}",
        "SECRET_KEY": "disposable-migration-proof",
    })
    try:
        with engine.connect() as connection:
            connection.execute(text(f"CREATE SCHEMA {quoted_schema}"))
        schema_0026: set[tuple[str, str]] = set()
        for revision in EXPECTED_CHAIN:
            _run([sys.executable, "-m", "flask", "--app", "app", "db", "upgrade", revision], env)
            with engine.connect() as connection:
                actual = connection.execute(text(
                    f"SELECT version_num FROM {quoted_schema}.alembic_version"
                )).scalar_one()
            evidence["upgrades"].append({"target": revision, "actual": actual, "ok": actual == revision})

            if revision == "0026_programming_exposure_roles":
                with engine.begin() as connection:
                    connection.execute(text(
                        f"INSERT INTO {quoted_schema}.athletes "
                        "(id, created_at, updated_at, first_name, last_name, email, status) "
                        "VALUES (27001, '2026-01-01', '2026-01-01', 'Legacy', "
                        "'Athlete', 'legacy-0026@example.test', 'active')"
                    ))
                    schema_0026 = set(connection.execute(text("""
                        SELECT table_name, column_name
                        FROM information_schema.columns
                        WHERE table_schema=:schema
                    """), {"schema": schema}).all())

        with engine.connect() as connection:
            schema_0027 = set(connection.execute(text("""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema=:schema
            """), {"schema": schema}).all())
            legacy = connection.execute(text(
                f"SELECT organisation_id FROM {quoted_schema}.athletes "
                "WHERE id=27001"
            )).one()
            not_valid_fks = connection.execute(text("""
                SELECT count(*) FROM pg_constraint c
                JOIN pg_namespace n ON n.oid=c.connamespace
                WHERE n.nspname=:schema AND c.contype='f' AND NOT c.convalidated
            """), {"schema": schema}).scalar_one()
            tenant_indexes = connection.execute(text("""
                SELECT count(*) FROM pg_indexes
                WHERE schemaname=:schema AND indexname LIKE 'ix_%_organisation_id'
            """), {"schema": schema}).scalar_one()
            assignment_table_exists = connection.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema=:schema
                      AND table_name='coach_athlete_assignments'
                )
            """), {"schema": schema}).scalar_one()
        evidence["expansion"] = {
            "legacy_row_preserved": tuple(legacy) == (None,),
            "no_columns_removed": schema_0026 <= schema_0027,
            "columns_added": len(schema_0027 - schema_0026),
            "not_valid_foreign_keys": not_valid_fks,
            "tenant_indexes": tenant_indexes,
            "assignment_table_deferred": not assignment_table_exists,
        }

        verifier = _run([
            sys.executable,
            str(REPO_ROOT / "scripts" / "migrations" / "saas_tenancy_verify.py"),
            "--database-url", database_url,
            "--phase", "expand",
            "--expected-head", EXPECTED_HEAD,
        ], env)
        evidence["verifier"] = json.loads(verifier)
        _run([
            sys.executable, "-m", "flask", "--app", "app", "db",
            "downgrade", "0026_programming_exposure_roles",
        ], env)
        with engine.connect() as connection:
            downgraded_head = connection.execute(text(
                f"SELECT version_num FROM {quoted_schema}.alembic_version"
            )).scalar_one()
            downgraded_schema = set(connection.execute(text("""
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema=:schema
            """), {"schema": schema}).all())
            legacy_count = connection.execute(text(
                f"SELECT count(*) FROM {quoted_schema}.athletes WHERE id=27001"
            )).scalar_one()
        evidence["disposable_downgrade"] = {
            "head": downgraded_head,
            "restored_0026_shape": downgraded_schema == schema_0026,
            "legacy_row_preserved": legacy_count == 1,
        }
        expansion_ok = (
            evidence["expansion"]["legacy_row_preserved"]
            and evidence["expansion"]["no_columns_removed"]
            and evidence["expansion"]["not_valid_foreign_keys"] > 0
            and evidence["expansion"]["tenant_indexes"] > 0
            and evidence["expansion"]["assignment_table_deferred"]
            and evidence["disposable_downgrade"]["head"] == "0026_programming_exposure_roles"
            and evidence["disposable_downgrade"]["restored_0026_shape"]
            and evidence["disposable_downgrade"]["legacy_row_preserved"]
        )
        evidence["ok"] = all(item["ok"] for item in evidence["upgrades"]) and evidence["verifier"]["ok"] and expansion_ok
        return evidence
    finally:
        with engine.connect() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE"))
        evidence["cleaned_up"] = True
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-postgres", action="store_true",
        help="fail instead of reporting a skip when POSTGRES_TEST_DATABASE_URL is unset",
    )
    args = parser.parse_args(argv)
    report: dict[str, Any] = {"migration_graph": migration_graph()}
    database_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if database_url:
        report["postgres"] = database_proof(database_url)
    else:
        report["postgres"] = {"status": "skipped", "reason": "POSTGRES_TEST_DATABASE_URL is unset"}
    print(json.dumps(report, indent=2))
    graph_ok = report["migration_graph"]["ok"]
    postgres_ok = report["postgres"].get("ok", not args.require_postgres)
    return 0 if graph_ok and postgres_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
