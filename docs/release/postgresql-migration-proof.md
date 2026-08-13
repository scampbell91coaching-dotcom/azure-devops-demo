# Disposable PostgreSQL migration proof

This package proves the Powerlifting portal's exact Alembic tail
`0019 -> 0020 -> 0021 -> 0022 -> 0023`. It does not authorize or target
production, Azure, Argo, or a live database.

## Static proof (always available)

From the repository root:

```bash
python scripts/migrations/postgres_migration_proof.py
pytest -q scripts/migrations/tests
```

The command fails unless Alembic exposes exactly one head,
`0023_organisation_invitation_delivery`, and each revision in the tail declares
the preceding revision as its parent. With no test URL it reports PostgreSQL as
skipped; it never falls back to `DATABASE_URL`.

## Disposable PostgreSQL proof

Point the test-only variable at a PostgreSQL database intended for disposable
tests. The role must be able to create and drop schemas and create objects
inside them. Do not use a production, shared staging, or application runtime
credential.

```bash
export POSTGRES_TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost/TEST_DATABASE'
python scripts/migrations/postgres_migration_proof.py --require-postgres \
  > /tmp/powerlifting-postgres-migration-proof.json
```

The runner creates a random `pl_migration_proof_*` schema, sets that schema as
the connection search path, and performs these observable gates:

1. upgrade a blank schema to `0019_meal_plan_delivery` and assert its recorded
   version is exactly 0019;
2. upgrade separately to 0020, 0021, 0022, and 0023, asserting the version after
   every step (the evidence therefore proves upgrade-from-0019, not merely an
   empty-to-head migration);
3. at 0023, run the independent verifier in a PostgreSQL read-only transaction;
4. require the canonical tenancy/control tables (`organisations`,
   `organisation_memberships`, `coach_athlete_ownerships`,
   `organisation_invitations`, billing tables, and support tables), and reject
   removed duplicate American-spelling and legacy membership table families;
5. require one `alembic_version` row at the canonical head and check tenant
   constraints/indexes; and
6. drop the random schema in a `finally` block, including after a failed gate.

The verifier reports `transaction_is_read_only` from PostgreSQL's own
`SHOW transaction_read_only` value. It performs catalog and aggregate `SELECT`
queries only and explicitly rolls the transaction back. A non-zero exit is a
failed proof; do not stamp or edit migration history to bypass it.

Expected evidence contains five ordered `upgrades` entries whose `target`,
`actual`, and `ok` fields show 0019 through 0023, plus a successful verifier
result. The output intentionally contains the disposable schema name but does
not echo the database URL or credentials.
