# Data backup and restore evidence expectations

Configured backup is not proven recovery. The repository declares Azure
PostgreSQL Flexible Server PITR with seven-day retention, no geo-redundant
backup and no HA, but contains no recorded database restore exercise or formal
RPO/RTO. A pod replacement test is not database restore evidence.

This checklist defines acceptance evidence; it does not authorize live Azure,
DNS, Key Vault, production database or application changes.

## Before relying on backup

- [ ] Business owner approves beta RPO, RTO, seven-day retention and the
  single-region/no-geo-backup failure boundary.
- [ ] Database restore owner and backup are named, reachable and authorized;
  approval and escalation paths are documented.
- [ ] Read-only inventory records source server identifier, region, backup
  policy/retention, earliest/latest usable restore points and UTC observation
  time without credentials or connection strings.
- [ ] Evidence maps every authoritative beta data store. Redis/session state,
  Git, screenshots and application pods are not treated as athlete-data backups.
- [ ] Retention is long enough for detection, decision and restore rehearsal;
  evidence has an expiry no later than the next material schema/infrastructure
  change or the agreed exercise interval.

## Restore exercise

Exercise outside production with separate approval and a production-shaped,
sanitized source where possible.

- [ ] Record approved restore point, why it tests the RPO, source and new target
  identifiers, start/end UTC times, operator and approver.
- [ ] Restore to a **new** server. Preserve the source; do not overwrite it or
  switch production connections during a readiness exercise.
- [ ] Establish approved private networking/DNS and separate credentials without
  printing secrets or weakening access controls.
- [ ] Validate PostgreSQL version/extensions, expected migration head, table and
  row-count invariants, tenant ownership constraints and referential integrity.
- [ ] Start an isolated candidate application against the restored target and
  run synthetic tenant-isolation and coach/athlete smoke tests, including a
  write/reload. Prevent email, webhook and other external side effects.
- [ ] Measure backup-point data loss and total recovery time against RPO/RTO;
  record pass/fail and unexplained discrepancies.
- [ ] Prove the connection cutover and reversal procedure in the isolated
  environment, including runtime and migration credentials, while never
  exposing values.
- [ ] Retire the restored server and temporary credentials under an approved,
  verified cleanup plan after evidence retention is secured.

## Evidence bundle

Retain a redacted, access-controlled bundle containing:

- exercise plan, approvals, owner, release/schema revisions and timestamps;
- backup inventory metadata and restore operation status/IDs;
- sanitized command outcomes and logs, not secrets or database contents;
- schema/integrity/count assertions and tenant-isolation results;
- smoke-test results, measured RPO/RTO, failures and remediation owners;
- target cleanup confirmation and evidence expiry; and
- independent reviewer sign-off stating exactly what failure domains were and
  were not tested.

Screenshots alone, a successful Azure restore status, a database connection, or
an application health response are insufficient. Acceptance requires usable
powerlifting data, authorization isolation and representative read/write paths.
Until the exercise passes and is reviewed, release acceptance must say
**backup configured; restore readiness unproven** and the shared multi-coach
beta remains NO-GO.
