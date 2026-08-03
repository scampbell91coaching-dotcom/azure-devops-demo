# PostgreSQL migration foundation

The coaching app now uses Flask-Migrate/Alembic for schema changes. Normal web
startup neither creates or alters tables nor inserts programming seed data.
SQLite remains the fallback when `DATABASE_URL` is unset, and PostgreSQL is
selected by setting `DATABASE_URL` to a Psycopg URL such as
`postgresql+psycopg://user:password@localhost/database`.
Plain `postgresql://` and legacy `postgres://` URLs are normalized to the
Psycopg 3 driver automatically.

This foundation does **not** copy SQLite data, change production configuration,
or deploy anything.

## Empty database workflow

Run commands from `platform-portal`:

```bash
export DATABASE_URL='postgresql+psycopg://user:password@localhost/empty_database'
flask --app app db upgrade
flask --app app seed-programming
flask --app app verify-schema
```

`db upgrade` applies the reviewed baseline schema. `seed-programming` is
idempotent and inserts the built-in competition exercises and day templates.
`verify-schema` checks that every table and column in the coaching model
metadata exists in the selected database.

Always verify that `DATABASE_URL` names the intended empty database before
running the upgrade. No command in this change copies data from
`data/platform-history.db`.

## Existing SQLite coaching database

The baseline migration creates the complete current schema and is intended for
an empty database. Do not run it directly against an existing populated SQLite
database because its tables already exist.

For a legacy database, first back it up, run `flask --app app verify-schema`,
and review any reported differences. Once the schema is confirmed to match the
baseline, record the revision without executing DDL:

```bash
flask --app app db stamp 0001
```

The retained `ensure_exercise_knowledge_columns()` and
`ensure_prescription_mode_columns()` helpers support a temporary compatibility
mode. Set `LEGACY_STARTUP_INITIALIZATION=True` only in an explicit configuration
when old startup behavior is required. It defaults off outside tests; tests keep
the compatibility behavior unless they set the flag to false.

## Development and migration review

After changing a coaching model, generate a revision and inspect both upgrade
and downgrade operations before applying it:

```bash
flask --app app db migrate -m 'describe schema change'
flask --app app db upgrade
flask --app app verify-schema
```

Alembic sees all models through `portal.models`, including coaching
applications, athletes, check-ins, programming, the exercise library, lead
captures, and platform snapshots. The separate public application database is
not part of this migration environment.
