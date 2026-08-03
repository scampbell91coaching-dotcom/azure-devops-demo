#!/usr/bin/env python3
"""Safely reset the dedicated loopback PostgreSQL integration-test database."""

from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit, urlunsplit

DATABASE_NAME = "traditional_strength_test"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def validate_url(value: str) -> tuple[str, str]:
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgres", "postgresql", "postgresql+psycopg"}:
        raise ValueError("POSTGRES_TEST_DATABASE_URL must be a PostgreSQL URL")
    if parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError("database host must be localhost, 127.0.0.1, or ::1")
    if parsed.path != f"/{DATABASE_NAME}":
        raise ValueError(f"database name must be exactly {DATABASE_NAME}")
    if not parsed.username:
        raise ValueError("database URL must include a PostgreSQL user")
    driver_scheme = "postgresql+psycopg"
    target = urlunsplit((driver_scheme, parsed.netloc, parsed.path, parsed.query, ""))
    maintenance = urlunsplit((driver_scheme, parsed.netloc, "/postgres", parsed.query, ""))
    return target, maintenance


def reset_database(value: str) -> None:
    _, maintenance_url = validate_url(value)

    from sqlalchemy import create_engine, text

    engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                     "WHERE datname = :name AND pid <> pg_backend_pid()"),
                {"name": DATABASE_NAME},
            )
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{DATABASE_NAME}"')
            connection.exec_driver_sql(f'CREATE DATABASE "{DATABASE_NAME}"')
    finally:
        engine.dispose()


def main() -> int:
    value = os.getenv("POSTGRES_TEST_DATABASE_URL", "")
    if not value:
        print("db-reset: POSTGRES_TEST_DATABASE_URL is not set", file=sys.stderr)
        print("db-reset: see docs/local-development.md; the URL value is never printed", file=sys.stderr)
        return 1
    try:
        reset_database(value)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"db-reset: refused or unable to reset database: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # Database drivers expose several connection error types.
        print(f"db-reset: database operation failed ({type(exc).__name__}); URL hidden", file=sys.stderr)
        return 1
    print(f"Reset local PostgreSQL database {DATABASE_NAME}; no remote system was contacted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
