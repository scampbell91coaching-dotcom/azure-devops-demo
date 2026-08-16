# Warm-up Factory Integration / PostgreSQL Proof Handoff

Date: 2026-08-15 (Europe/London)

## Outcome

**BLOCKED for PostgreSQL proof and commit.** The repair is implemented and the
focused application/security suite passes, but this sandbox will not permit a
PostgreSQL server socket and cannot access the Docker daemon. Per the task
instruction, PostgreSQL success is not inferred from SQLite evidence. No commit
was created because the required PostgreSQL evidence is incomplete.

Base/working HEAD: `b4b84db`

## Implemented repair

- Added the supported coach form/route flow for a whole-session target or an
  explicit lift-slot target, including rejection of a slot from another session.
- Added nullable `warmup_assignments.lift_slot_id`, indexed, with a foreign key to
  `programming_lift_slots.id` and `ON DELETE CASCADE`. Thus legacy/general rows
  remain nullable and deleting a lift slot removes only its targeted delivery;
  it cannot silently become session-general.
- Factory acceptance now pins one generated session-general protocol plus one
  targeted generated protocol for every S/B/D lift slot.
- Moved snapshot freezing from athlete GET to the first successful athlete set
  save. Empty plans are not frozen. The snapshot participates in the same
  transaction as the training save.
- Added request-level evidence that a non-empty snapshot is frozen on first save
  and remains unchanged after a later protocol edit.
- Existing coach-pin precedence, proposal replay/idempotency, composition, and
  tenancy denial coverage remains passing in the focused suite.

## PostgreSQL availability and exact blocker

Client/server binary version:

```text
$ psql --version
psql (PostgreSQL) 18.4 (Ubuntu 18.4-0ubuntu0.26.04.1)

$ /usr/lib/postgresql/18/bin/postgres ...
starting PostgreSQL 18.4 (Ubuntu 18.4-0ubuntu0.26.04.1)
```

Availability checks/results:

```text
$ docker version --format '{{.Server.Version}}'
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock

$ pg_isready
/var/run/postgresql:5432 - no response
```

A disposable cluster was successfully initialized in
`/tmp/warmup-pg-proof.EdrRuI/data`, then both permitted connection mechanisms
were attempted:

```text
$ postgres -D /tmp/warmup-pg-proof.EdrRuI/data -k /tmp/warmup-pg-proof.EdrRuI -p 55432
FATAL: could not create any TCP/IP sockets

$ postgres -D /tmp/warmup-pg-proof.EdrRuI/data -k /tmp/warmup-pg-proof.EdrRuI -p 55432 -c listen_addresses=''
could not bind Unix address "/tmp/warmup-pg-proof.EdrRuI/.s.PGSQL.55432": Operation not permitted
FATAL: could not create any Unix-domain sockets
```

Therefore the required PostgreSQL 0024→0025→0024→0025 execution, PostgreSQL
`current`, catalog inspection, legacy-row mutation, and live deletion proof are
**BLOCKED**.

## Migration inspection and supplementary SQLite evidence

Migration inspected: `platform-portal/migrations/versions/0025_warmup_lift_slot_target.py`

Revision chain:

```text
revision = 0025_warmup_lift_slot_target
down_revision = 0024_pdf_meal_plan_delivery
```

Exact supplementary command sequence (not substituted for PostgreSQL):

```bash
export DATABASE_URL="sqlite:////tmp/<disposable>.db"
export SECRET_KEY=migration-proof
python -m flask --app portal:create_app db heads
python -m flask --app portal:create_app db upgrade
python -m flask --app portal:create_app db current
# SQLAlchemy inspect columns, foreign keys, and indexes
python -m flask --app portal:create_app db downgrade 0024_pdf_meal_plan_delivery
python -m flask --app portal:create_app db current
python -m flask --app portal:create_app db upgrade 0025_warmup_lift_slot_target
python -m flask --app portal:create_app db current
```

Results:

```text
0025_warmup_lift_slot_target (head)
columns [('lift_slot_id', True)]
foreign_keys [('fk_warmup_assignments_lift_slot_id', ['lift_slot_id'],
               'programming_lift_slots', {'ondelete': 'CASCADE'})]
indexes [('ix_warmup_assignments_lift_slot_id', ['lift_slot_id'])]
legacy_nullable_insert_schema_accepts_null yes
0024_pdf_meal_plan_delivery
0025_warmup_lift_slot_target (head)
```

This proves a sole Alembic head and a reversible migration on the supplementary
backend. PostgreSQL `current` remains blocked as described above.

## Focused tests

The repository did not contain a local environment, and the system Python lacked
Flask. A pre-existing read-only-compatible project virtualenv was used:
`/home/steve/azure-devops-demo/platform-portal/.venv/bin/python`.

```bash
/home/steve/azure-devops-demo/platform-portal/.venv/bin/python -m compileall -q \
  platform-portal/portal \
  platform-portal/migrations/versions/0025_warmup_lift_slot_target.py

/home/steve/azure-devops-demo/platform-portal/.venv/bin/pytest -q \
  platform-portal/tests/test_warmup_integration.py \
  platform-portal/tests/test_warmup_plans.py \
  platform-portal/tests/test_movement_warmup_candidates.py \
  platform-portal/tests/test_block_factory_v2.py \
  platform-portal/tests/test_block_factory_v3.py \
  platform-portal/tests/test_warmup_migration.py \
  platform-portal/tests/test_v79_authorization_boundaries.py \
  platform-portal/tests/test_cross_tenant_security.py \
  platform-portal/tests/test_coaching_route_security.py
```

Result:

```text
131 passed in 18.44s
```

Focused rerun of changed integration/factory/migration coverage:

```text
35 passed in 7.44s
```

## Git state

`git diff --check` passes with no output. No deploy, push, or main-branch action
was performed. No commit SHA exists because PostgreSQL proof is blocked; the
intended changes and this handoff remain in the worktree for continuation in an
environment that permits PostgreSQL sockets.
