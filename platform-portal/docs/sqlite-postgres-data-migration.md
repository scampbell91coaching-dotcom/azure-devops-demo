# SQLite-to-PostgreSQL data migration

This runbook migrates the coaching database `data/platform-history.db`. It never
uses `public-leads.db`, provisions infrastructure, changes secrets, deploys, or
modifies the SQLite source. Run it only against an isolated, non-production
PostgreSQL database first.

## Policy and prerequisites

- Back up the SQLite file and PostgreSQL database, verify both backups, and
  record their checksums before starting.
- Stop application writes or take a consistent copy of SQLite before the final
  run. The tool opens its source read-only but cannot prevent another process
  from changing it concurrently.
- Install the application dependencies, including `psycopg`.
- Export `TARGET_DATABASE_URL` for the intended PostgreSQL database. The report
  records only its host and database name, never credentials.
- The source must contain every application table and column in current
  SQLAlchemy metadata. The target must already have the current Alembic schema.
- Reference data (`exercises`, `day_templates`, and
  `day_template_exercises`) is migrated from SQLite. Do **not** seed first.
  Run `seed-programming` only after migration if its idempotent additions are
  wanted. `alembic_version` is schema metadata and is not copied or included in
  row-count equality.

## Prepare and upgrade the target

Point the Flask application at the target only for schema operations:

```bash
DATABASE_URL="$TARGET_DATABASE_URL" flask --app app db upgrade
DATABASE_URL="$TARGET_DATABASE_URL" flask --app app verify-schema
```

The migration independently verifies the same metadata contract and also
requires `alembic_version`. It refuses any application rows by default.

## Dry run

Dry run opens both databases, validates source and target schemas, counts every
application table, verifies source foreign keys and uniqueness, and writes a
report. It inserts nothing and does not reset sequences.

```bash
flask --app app migrate-sqlite-data \
  --source data/platform-history.db \
  --target "$TARGET_DATABASE_URL" \
  --report /tmp/migration-dry-run-report.json \
  --dry-run
```

Progress is emitted as one JSON object per line. A report is written on success
or failure.

## Real migration

After reviewing the dry-run report and confirming the target identity:

```bash
flask --app app migrate-sqlite-data \
  --source data/platform-history.db \
  --target "$TARGET_DATABASE_URL" \
  --report /tmp/migration-report.json
```

Rows are inserted parent-first in SQLAlchemy dependency order with explicit
IDs. PostgreSQL performs type conversion for booleans, dates, datetimes,
numbers, text, and nulls. Copy, sequence resets, and target verification share
one transaction; an error rolls the transaction back and no row is silently
skipped.

## Verification

Require `status: completed`, no errors, equality for every row count, zero
orphans and duplicate unique values, successful representative reads, and a
sequence result for each integer primary key. Then run:

```bash
DATABASE_URL="$TARGET_DATABASE_URL" flask --app app verify-schema
```

In a local staging instance, read athletes, weekly check-ins, training blocks,
weeks, sessions, prescriptions, exercises, and nutrition check-ins through the
normal application screens/API. Compare a sample of IDs, timestamps, nulls,
ordering positions, and numeric values to the backed-up SQLite copy.

## Local target reset and explicit rerun

Prefer dropping and recreating a dedicated local test database, then run
`flask --app app db upgrade` again. Never use this procedure in production.

For a controlled rerun, the only supported in-tool mode is:

```bash
flask --app app migrate-sqlite-data \
  --source data/platform-history.db \
  --target "$TARGET_DATABASE_URL" \
  --report /tmp/migration-rerun-report.json \
  --allow-non-empty --replace-existing
```

Both flags are required. This deletes only metadata-listed application rows,
child-first, then recopies and verifies them in one transaction. Failure
restores the target's prior rows. `--allow-non-empty` alone is intentionally
insufficient because mixing seed or historical rows makes count verification
ambiguous.

## Rollback

Before cutover, migration failures roll back automatically. After a successful
migration, rollback means keeping the application on SQLite or restoring the
verified PostgreSQL backup; the tool does not switch application configuration.
Preserve the source and all reports until the retention period expires.

## Known limitations

- The source must match current application metadata; this is a deliberate
  fail-closed migration, not a legacy schema transformer.
- The operation takes a single source pass and requires application writes to
  be quiesced for a consistent cutover snapshot.
- Very large tables are currently materialized one table at a time rather than
  streamed. This platform-specific tool is not a replication framework.
- Cyclic foreign-key schemas are unsupported.
- PostgreSQL integration tests run only when `POSTGRES_TEST_DATABASE_URL` is
  present and points to a disposable database where test schemas may be made.

## Azure cutover plan (planning only)

Provisioning is outside this tool. Once an approved Azure PostgreSQL target and
secret-management process exist: rehearse against an isolated clone, measure
downtime, back up both sides, stop writes, take the final SQLite copy, upgrade
the target schema, dry-run, migrate, verify the report and application reads,
then change the application database secret through the normal reviewed release
process. Keep the previous deployment configuration and SQLite backup ready for
rollback. This repository change performs none of those Azure or deployment
actions.
