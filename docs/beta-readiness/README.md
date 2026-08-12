# Powerlifting multi-coach beta readiness package

**Status:** conditional package; **the shared multi-coach beta is currently NO-GO**.

This package is the operating record for a closed Traditional Strength
powerlifting beta. It does not make the product ready by itself. At the time of
writing, organisation membership and tenant-qualified authorization are future
contracts, the cross-tenant browser probes are disabled, and no recorded
PostgreSQL restore exercise or formal RPO/RTO is present in the repository.
Those are release evidence gaps, not checklist items that may be waived.

Until tenant isolation is implemented and independently accepted, use the
existing [single-coach supervised pilot](../v7.4-supervised-pilot-runbook.md)
only. Do not put coaches from different businesses, or their athletes, in one
shared application/database boundary.

## Package map

| Record | Use |
| --- | --- |
| [Beta boundaries](boundaries-and-limitations.md) | Permitted cohort and features, disabled capabilities, known limitations |
| [Onboarding](onboarding-checklist.md) | Set up each approved coach and athlete without assuming unattended delivery |
| [Release acceptance](release-acceptance-checklist.md) | Evidence-based go/no-go decision for a specific immutable release |
| [Coach/athlete smoke test](smoke-test-checklist.md) | Powerlifting money-path verification using synthetic accounts first |
| [Support and incidents](support-and-incident-runbook.md) | Support intake, containment, forward repair, recovery and communication |
| [Backup/restore evidence](backup-restore-evidence.md) | Minimum evidence for relying on PostgreSQL PITR; does not authorize a restore |

## Decision rule

The beta decision owner records one outcome for a named release and cohort:

- **GO:** all mandatory gates pass with linked, redacted evidence;
- **CONTAINED GO:** only a limitation explicitly allowed by the boundary
  document remains, with an owner, expiry and tested manual containment; or
- **NO-GO:** any isolation, authentication, data integrity, backup, support or
  core coaching-path gate lacks evidence or fails.

Silence, screenshots without provenance, historical test results, a healthy
`/health` endpoint, or a configured backup policy are not proof. Evidence must
name the release, environment, UTC time, actor/owner, expected result and actual
result. Store beta participant data and operational evidence only in approved
private systems; never commit identities, credentials, invitation URLs, health
details, database contents or production logs.

## Required ownership

Before any go decision, name the beta decision owner, product owner, coaching
owner, release operator, security/tenant-isolation approver, incident commander,
support responder, database restore owner and participant-communications owner.
One person may hold several roles, but every role needs a reachable backup and
an agreed response window.

This documentation does not authorize production, Argo CD, Azure or database
changes. Follow the separately approved operational procedures for any live
action.
