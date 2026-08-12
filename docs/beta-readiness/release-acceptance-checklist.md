# Beta release acceptance checklist

Create one immutable record per candidate release. This supplements, and does
not replace, the repository [release checklist](../release/release-checklist.md).

## Record

- Candidate commit/image digest:
- Environment and configuration revision:
- Intended tenant(s), coaches and maximum athletes:
- Decision owner and UTC decision time:
- Evidence location and retention/expiry:
- Outcome: GO / CONTAINED GO / NO-GO

## Mandatory release evidence

- [ ] Candidate is an immutable, reviewed revision; generated release evidence
  identifies the same clean commit and reports ready.
- [ ] Focused unit/integration tests and the guarded Playwright release suite pass
  against disposable data; failures/skips are explained, not ignored.
- [ ] Migration head, compatibility with the retained image, lock/duration
  budget and forward-repair owner are accepted for database-changing releases.
- [ ] Tenant membership and tenant-qualified access are implemented; automated
  cross-tenant read and mutation probes cover athlete, programme, session,
  result, check-in, report/export and invitation identifiers.
- [ ] Cross-tenant probes pass for two tenants, multiple coaches and athletes,
  including direct IDs and list/search surfaces. No test is a placeholder or
  enabled merely by changing an environment flag.
- [ ] Anonymous, athlete, coach, tenant-owner and support roles have documented
  allow/deny results; authorization failures have no side effects or data leaks.
- [ ] Synthetic coach/athlete smoke checklist passes through the real deployed
  edge and PostgreSQL path on supported desktop and phone browsers.
- [ ] Invitation hostname, expiration, single use, revocation and delivery/fallback
  path are proven in the target environment without capturing tokens.
- [ ] Operational signals for authentication, 5xx, database errors and latency
  are observable; alert/support routing is tested or a named supervised manual
  watch is approved for the entire beta window.
- [ ] Backup inventory is current and the backup/restore evidence checklist has
  an accepted, production-shaped restore exercise within the agreed validity
  period. Formal beta RPO/RTO and restore authority are recorded.
- [ ] Rollback/forward-repair plan names the retained compatible image, decision
  owner, stop conditions and post-repair verification. No automatic schema
  downgrade or in-place database restore is assumed.
- [ ] Support coverage, incident commander, participant communications, privacy
  handling and cohort freeze/exit procedure are confirmed.
- [ ] Known limitations and feature flags match the approved boundaries; all
  forbidden capabilities remain inaccessible, including by direct URL/API.

## Acceptance test

- [ ] No open severity-one/two incident, unexplained data discrepancy, isolation
  failure, failed migration, missing backup evidence or unresolved smoke failure.
- [ ] Every containment has an owner, explicit cohort limit, participant impact,
  expiry and evidence that it works.
- [ ] A second reviewer signs tenant-isolation and restore evidence separately
  from the person who produced it.
- [ ] Decision and evidence expiry are communicated. Expired evidence changes
  the outcome to NO-GO until renewed.

Current repository evidence does not satisfy the tenant-isolation or recorded
restore gates. Therefore this checklist cannot currently produce GO for a
shared multi-coach beta.
