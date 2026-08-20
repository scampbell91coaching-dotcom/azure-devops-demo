# Tenancy tranche 1 expansion contract

Migration `0027_tenancy_ownership_expand` is schema expansion only. It follows
`0026_programming_exposure_roles` and leaves the migration tree with one head.
Production rollback is forward repair; the Alembic downgrade exists only for
disposable development and migration-test schemas.

The migration adds nullable `organisation_id` ownership to the athlete root and
its persisted check-in, state, programming, nutrition, meet, warm-up, meal-plan,
structural nullable
organisation/user targets beside the legacy opaque support references, and
nullable session/authorization generation counters on users, organisation
memberships, and support principals. Existing PDF meal plans and SaaS control
tables already have organisation ownership and are not duplicated.

No value is derived or populated. Existing uniqueness rules, legacy ownership,
opaque support references, login roles, route behavior, and write paths remain
unchanged. PostgreSQL foreign keys on populated tables are installed `NOT VALID`;
they protect future non-null writes without scanning or classifying legacy rows.
Indexes on new ownership keys are built concurrently on PostgreSQL.

Tranche 1 does not claim tenant isolation. Backfill, composite tenant-qualified
foreign keys, constraint validation, non-null enforcement, assignment cutover,
authorization/session consumption, RLS, and tenant-aware routes are explicitly
deferred. Do not validate or constrain these nullable keys until a separately
reviewed deterministic backfill has classified every legacy row.

Verification is provided by `scripts/migrations/postgres_migration_proof.py`
and the read-only `scripts/migrations/saas_tenancy_verify.py --phase expand`.
The proof upgrades an isolated genuine 0026 schema containing an old-style row,
then proves the row remains unassigned, all 0026 columns remain, and the new
foreign keys/indexes exist.
