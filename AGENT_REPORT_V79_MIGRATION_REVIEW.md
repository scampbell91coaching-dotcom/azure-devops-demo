# V7.9 database and migration review report

## Outcome

Completed a design-only review and produced
`docs/v7.9-migration-sequencing.md`. No Alembic migration, model, application,
test, deployment or infrastructure file was changed.

The reviewed repository has one Alembic head:
`0015_client_services`. The recommended sequence is a macro-prescription expand
revision based on that accepted head, followed by a meal-plan persistence expand
revision, followed only later by measured data migration/read retirement and
contract revisions.

## Principal decisions

- Keep both V7.9 schema changes additive so the old application remains safe on
  the expanded schema. New application paths must remain gated on schema
  readiness because a new app on the old schema is not safe.
- Persist macro prescriptions before meal plans. Meal assignments reference an
  immutable prescription and also snapshot the targets used at publication.
- Enforce inclusive effective-date non-overlap transactionally in PostgreSQL,
  preferably with a GiST exclusion constraint; application-only checks race.
- Treat prescriptions, published assignments, overrides, substitutions and
  adherence as append-only history. Corrections create successor records/events.
- Do not promote copied legacy check-in targets into prescriptions. They lack
  authoritative provenance and remain historical snapshots during transition.
- Nutrition entitlement gates future actions/access, not historical retention.
  Revocation must not delete audit or assignment history.
- Roll application code back while leaving additive schema in place. After
  writes start, use a new forward-fix migration rather than destructive automatic
  downgrade.
- The production Helm hook runs the candidate image's `flask db upgrade` with no
  retry and a ten-minute deadline, but does not verify constraints/indexes/heads.
  Promotion needs explicit one-head, ancestry and post-upgrade integrity gates.

## Evidence inspected

- all Alembic revision identifiers and parent links, plus `flask db heads` and
  verbose history output;
- macro-prescription and meal-plan domain services and their V7.3 design docs;
- client-service entitlement model, migration and effective-history resolver;
- migration tests, schema verifier, app startup/model registration behavior;
- Helm migration Job, Deployment rollout strategy and production values.

## Verification

```text
flask --app app db heads
0015_client_services (head)
```

Final scope checks should show only this report and the sequencing document in
the commit. Migration graph behavior was inspected but no migration was added or
modified.

