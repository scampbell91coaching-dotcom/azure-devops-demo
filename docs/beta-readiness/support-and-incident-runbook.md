# Beta support and incident/forward-repair runbook

## Support intake

Use the agreed private support channel. Record ticket ID, UTC/local time,
release, tenant-safe participant reference, role, route/action, device/browser,
expected/actual result and sanitized correlation ID. Ask for the minimum data
needed. Never request a password, invitation/reset URL, OAuth token, database
value or unredacted athlete health/training screenshot.

Classify before troubleshooting:

- **SEV-1:** suspected cross-tenant/cross-athlete disclosure or mutation,
  account takeover, widespread data loss/corruption, or unsafe prescription
  mismatch affecting active sessions;
- **SEV-2:** cohort-wide authentication/write failure, repeated missing/duplicate
  logs, inability to retrieve completed training, or failed recovery control;
- **SEV-3:** isolated workflow failure with a safe manual containment; or
- **SEV-4:** question, cosmetic defect or documented limitation.

SEV-1 freezes the whole beta. SEV-2 freezes affected tenants/new activity until
the incident commander explicitly resumes it. A limitation becomes an incident
when behavior exceeds the accepted containment.

## First response

1. Tell affected users to stop submitting; use the external channel for today's
   training instructions and urgent/pain concerns.
2. Start the incident record, name incident commander, technical owner,
   communications owner and next-update time.
3. Revoke exposed invitations/resets through supported controls. If account or
   tenant binding is uncertain, suspend affected access using an approved path.
4. Preserve relevant application/platform audit evidence and database state.
   Restrict access; do not delete logs or directly rewrite athlete records.
5. Determine blast radius using identifiers and metadata, not sensitive content:
   tenants, roles, routes, time window, release and read/write paths.
6. Freeze cohort growth, organisation invitations, exports/integrations and the
   affected write path. For isolation uncertainty, freeze all tenants.
7. Communicate what is known, what users must do, and the next update time. Do
   not speculate about data exposure or recovery completion.

## Diagnose and choose recovery

- Compare deployed immutable revision/configuration with accepted release
  evidence and identify the first failing request/change.
- Verify whether schema/data written by the candidate remains compatible with
  the retained application image.
- Prefer safe containment and a reviewed forward repair. Application rollback
  is valid only when the retained image is schema-compatible; it does not undo
  database writes.
- Do not run Alembic downgrade, ad-hoc SQL, in-place restore, direct GitOps patch
  or destructive cleanup as routine response. Database restore is a separate,
  authorized data-recovery decision and restores to a new server.

## Forward-repair checklist

- [ ] Reproduce with sanitized/synthetic data where possible and state the
  invariant that failed (tenant owner, session owner, immutable result, etc.).
- [ ] Identify all affected rows/objects without guessing ownership; quarantine
  ambiguous records and block the corresponding writes.
- [ ] Prepare the smallest additive repair, tests for the original failure and
  cross-tenant/non-regression coverage. Preserve audit history.
- [ ] Review migration compatibility, lock/duration, retry/idempotency and the
  consequences of partial execution.
- [ ] Test against a production-shaped sanitized restore when data/schema is
  involved; capture before/after counts and invariant checks.
- [ ] Promote through the normal reviewed immutable release path with an owner
  watching authentication, errors, database behavior and affected workflows.
- [ ] Re-run tenant isolation plus the full coach/athlete smoke test. Verify
  affected user-visible records with approved, privacy-safe methods.
- [ ] Resume one synthetic journey, then one named supervised participant, then
  the remaining cohort only after explicit incident-commander approval.

## Closure

- [ ] Participant impact, exposure decision, repair revision, evidence and
  remaining uncertainty are documented and communicated appropriately.
- [ ] Temporary access restrictions/flags are reviewed; forbidden beta features
  remain disabled.
- [ ] Follow-ups have owners and dates, including detection, test, runbook,
  privacy and participant-remediation work.
- [ ] The release/cohort acceptance decision is renewed; prior acceptance is not
  automatically restored when the service becomes healthy.
- [ ] Hold a blameless review for SEV-1/2 and retain only redacted evidence under
  the approved retention policy.
