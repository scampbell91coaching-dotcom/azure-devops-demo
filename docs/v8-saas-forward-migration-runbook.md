# V8 SaaS forward migration runbook

Status: executable release strategy; no production action is authorized by this
document. It complements `v8-saas-tenancy-architecture.md`. The repository head
at authoring time is `0019_meal_plan_delivery`; release operators must discover
and record the actual single head, never assume this value and never insert,
update, delete, or stamp `alembic_version` manually.

## Safety contract and invariants

The migration is expand/backfill/constrain/cut over, not a flag day. Existing
rows go to one deterministic organization (`traditional-strength-legacy`). Old
application binaries must keep working after every expand and backfill revision.
New binaries must tolerate nullable tenant keys until the contract release.

At every gate:

- take and identify a restorable database backup and rehearse restore outside
  production before the first release;
- prove Alembic has one head and that the candidate head descends from the
  deployed head (`flask db heads`, `flask db current`, `flask db history`);
- use the migration credential only in the migration job; runtime credentials
  must not bypass RLS or own tenant tables;
- stop when a reconciliation count is non-zero. Do not repair by stamping or
  editing `alembic_version`;
- do not use downgrade after tenant writes begin. Roll application code back on
  the additive schema, then ship a reviewed forward-repair revision.

The legacy organization ID must be a constant UUID recorded in the migration,
not generated on each run. Every data statement must be idempotent (`ON
CONFLICT` or an equivalent guarded update), bounded by primary-key ranges, and
commit between batches. The migration must select the owner user by an explicit
release input (immutable user ID plus normalized email cross-check); “first
coach” is not deterministic or safe.

## Ownership and constraint contract

Keep `users` global. Create `organizations`, `organization_memberships`, and
`coach_athlete_assignments` first. Use UUID organization/membership IDs,
timestamps and status checks. Required business keys are:

- unique `organizations(slug)`;
- unique `organization_memberships(organization_id, user_id)` and an index on
  `(user_id, status, organization_id)`;
- unique `coach_athlete_assignments(organization_id,
  coach_membership_id, athlete_id)` for the chosen history model, plus indexes
  beginning with `organization_id` and with `coach_membership_id`;
- unique `athletes(organization_id, id)` to support composite references, and
  `athletes(organization_id, lower(email))` if athlete email is tenant-local;
- a tenant-leading index on every tenant table and on its normal access paths,
  for example `(organization_id, athlete_id, submitted_at)`;
- composite unique parent keys and composite foreign keys
  `(organization_id, parent_id)` on every tenant-to-tenant edge. A scalar FK may
  coexist temporarily but is not the final isolation constraint.

All athlete-derived operational tables, including programming, logs, state,
check-ins, nutrition, warmups, meets, client services, account tokens,
prescriptions, programme revisions, external reviews, meal-plan assignments and
tenant-authored meal templates receive a materialized `organization_id`.
Acquisition records (`lead_captures`, `coaching_applications`) stay outside this
backfill until an acquisition-owner policy is approved. Catalogues and platform
telemetry remain global. The migration author must generate an ownership
inventory from the deployed schema and have the security owner approve any
exception before expand.

PostgreSQL uniqueness migration is progressive: create replacement unique
indexes with `CREATE UNIQUE INDEX CONCURRENTLY`, attach them with `USING INDEX`
where supported, then remove obsolete global business-key constraints only
after all deployed code uses tenant-qualified keys. Alembic revisions containing
`CONCURRENTLY` must use an autocommit block. Never hold a table rewrite or index
build in the ten-minute PreSync window.

## Release sequence

### R0 — evidence only

Record current image, application revision, Alembic current/head/history,
PostgreSQL version, row counts, largest tables, invalid constraints/indexes,
duplicate future business keys, owner user ID/email, and backup/restore evidence.
Exercise the verifier against a restored production copy. No production data is
changed.

### R1 — control-plane expand

The candidate Alembic revision creates the three control tables, status/check
constraints, indexes, and foreign keys. It inserts nothing. Add nullable
`athletes.organization_id` and optional `athletes.membership_id`; add nullable
`organization_id` to direct roots. Foreign keys are added `NOT VALID` on
PostgreSQL so creation does not scan populated tables. Do not add RLS or `NOT
NULL` yet.

The old application remains deployed. The PreSync job runs only short DDL and
then the read-only gate:

```sh
python scripts/migrations/saas_tenancy_verify.py \
  --phase expand --expected-head "$CANDIDATE_ALEMBIC_HEAD"
```

### R2 — compatible application and deterministic bootstrap

Deploy a compatibility binary that can read the legacy ownership path when
`organization_id` is null and, after bootstrap, dual-writes the resolved legacy
organization. It must never accept an organization ID from an untrusted form,
header or job payload without active-membership validation. All new objects get
an organization in the same transaction. Reads remain legacy-authoritative;
tenant-qualified shadow reads emit counts/metrics only. Existing coach UI and
programming workflows remain unchanged.

A small Alembic data revision may idempotently create the constant legacy
organization and explicit owner membership. It also creates active coach
memberships for other existing active coach users. Athlete-role users receive
an active athlete membership in the legacy organization, linked by the existing
`users.athlete_id`; profiles without logins remain organization-owned with null
membership. Abort on duplicate user/athlete links, a missing configured owner,
email mismatch, or more than one proposed owner.

### R3 — online backfill

Run an idempotent, resumable job outside Argo PreSync for large data movement.
Backfill in dependency order: athletes; direct athlete children; programming
block → week → session → prescriptions/logs/results; warmup/meet/nutrition
graphs; remaining tenant roots and children. Each child is populated from its
canonical parent, never from a session-selected organization. Each batch logs
range, examined, changed, already-correct and conflict counts without personal
data. A retry must be a no-op for completed rows.

The compatibility app continues dual-writing. Before advancing, run:

```sh
python scripts/migrations/saas_tenancy_verify.py --phase backfill \
  --expected-head "$CANDIDATE_ALEMBIC_HEAD"
```

### R4 — tenant-qualified application cutover

Switch reads one bounded workflow at a time behind a kill switch. Resolve the
active organization from an active membership, require coach assignment where
applicable, and query every object by organization plus ID. Background jobs
carry immutable organization/membership IDs and re-authorize at execution.
Compare shadow counts before each switch. Run two-organization negative tests
for route, service, repository and job paths. The kill switch returns reads to
the legacy-compatible path; it never permits unscoped global coach reads once a
second organization exists.

### R5 — validate and constrain

Build tenant-leading and replacement unique indexes concurrently before the
release sync. Validate each `NOT VALID` FK/check separately with monitored lock
and statement timeouts. Add composite FKs. Only after the backfill verifier is
clean, set tenant columns `NOT NULL`; prefer a validated `CHECK
(organization_id IS NOT NULL)` followed by `SET NOT NULL` to avoid a new scan.
Run the `constrain` verifier. Then enable and force RLS in a separate guarded
release after runtime `SET LOCAL app.organization_id` and connection-pool reset
tests pass. Owners/migration roles are not acceptable runtime roles.

### R6 — retirement

After a full rollback window with no legacy fallbacks or null writes, stop
dual-writing, remove global authorization meaning from `users.role` and later
retire `users.athlete_id` and obsolete scalar constraints in forward-only
revisions. Removal is never combined with the first tenant cutover.

## Argo PreSync ordering

The current private portal manifest has a candidate-image Argo `PreSync` job
with `backoffLimit: 0` and a 600-second deadline; it runs `flask db upgrade`, two
seeds, and `flask verify-production-db`. The Helm chart uses a pre-install/
pre-upgrade migration hook. Do not edit either manifest as part of this plan.

For each future release, publish the tested candidate image first, confirm the
desired Git revision/image out of band, then sync once. PreSync performs only
bounded expand/contract DDL and phase verification. A hook failure must prevent
Deployment reconciliation. Long backfills and concurrent index builds are
separately observed jobs completed before the next sync. Seeds must remain
tenant-neutral or explicitly legacy-scoped and idempotent. After PreSync,
observe old and new pods during rolling overlap; both versions must support the
current schema. Do not initiate another Argo sync while a migration or backfill
is active.

## Independent verification queries

Run these with a read-only role/transaction; capture counts, not row payloads:

```sql
SET TRANSACTION READ ONLY;
SELECT version_num FROM alembic_version; -- exactly one row; equals release head
SELECT slug, count(*) FROM organizations
 WHERE slug = 'traditional-strength-legacy' GROUP BY slug; -- one row/count 1
SELECT count(*) FROM organization_memberships m JOIN organizations o ON o.id=m.organization_id
 WHERE o.slug='traditional-strength-legacy' AND m.role='owner' AND m.status='active'; -- >= 1
SELECT count(*) FROM athletes WHERE organization_id IS NULL; -- 0 after R3
SELECT count(*) FROM users u WHERE u.role='coach' AND u.active AND NOT EXISTS
 (SELECT 1 FROM organization_memberships m WHERE m.user_id=u.id AND m.status='active'); -- 0
SELECT count(*) FROM users u JOIN organization_memberships m ON m.user_id=u.id
 JOIN athletes a ON a.id=u.athlete_id
 WHERE u.role='athlete' AND m.organization_id <> a.organization_id; -- 0
SELECT conrelid::regclass, conname FROM pg_constraint
 WHERE NOT convalidated AND contype IN ('f','c'); -- 0 before R5 completion
SELECT schemaname, tablename, policyname FROM pg_policies
 WHERE schemaname=current_schema() ORDER BY tablename, policyname; -- approved inventory after RLS
```

The supplied verifier generalizes the null, orphan, cross-tenant FK,
constraint-validation, nullability and index checks across catalog-discovered
tenant tables. Exit zero is necessary but not sufficient: release evidence also
requires row-count reconciliation, two-tenant negative tests, pool/RLS tests,
metrics, and restore evidence.

## Failure, rollback and forward repair

Before R4, stop the backfill, fix the cause, and resume from its checkpoint; an
additive old application rollback is safe. If R1/R2 partially commits, inspect
Alembic current/history and database objects, then repair with a new idempotent
forward revision. Never stamp around it. Preserve the legacy organization even
if application code rolls back.

During R4, disable only the affected tenant-qualified workflow if the
single-tenant fallback is still security-safe; otherwise fail closed and roll
back the binary while retaining schema/data. After a second organization or RLS
is active, never fall back to global coach authorization. Quarantine ambiguous
rows rather than guessing ownership, block affected writes, and forward-repair
from canonical parent/audit evidence. Do not delete organizations, memberships,
assignments, or tenant keys as rollback.

After R5, constraint or RLS failures are repaired forward. Temporarily disabling
RLS for ordinary runtime traffic is not a rollback. Use the audited migration
role for a bounded repair, rerun all gates, and record before/after aggregate
counts and the repair revision. Disaster recovery restores the whole database
to the rehearsed point and then reapplies known-good releases; it never edits
`alembic_version` independently of restored schema.
