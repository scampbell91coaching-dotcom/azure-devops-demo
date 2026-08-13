# Beta boundaries and known limitations

## Intended beta

The eventual beta is a small, named cohort of powerlifting coaches and their
assigned athletes validating the loop: athlete setup, coach-authored squat,
bench press and deadlift programming, publication, athlete set logging, session
completion, coach review, weekly check-in and deliberate programme adjustment.
It is not an open signup, self-service SaaS launch or generic sport platform.

Entry requires an accepted release record, a named support owner and an exit
plan for every participant. Cohort growth is a new go/no-go decision, not an
automatic consequence of a quiet week.

## Must remain disabled before tenant isolation acceptance

These capabilities remain off until organisation membership, tenant-qualified
lookups and cross-tenant denial are implemented and evidenced at route, service,
query and database boundaries:

- shared multi-coach access for coaches belonging to different businesses;
- organisation/workspace creation, switching, invitations and ownership transfer;
- a global coach directory, cross-coach athlete search or athlete reassignment;
- coach collaboration, impersonation or support access to another coach's data;
- organisation-wide exports, analytics, reporting or bulk operations;
- tenant-admin billing/entitlement controls and organisation lifecycle actions;
- tenant-scoped API tokens, integrations, webhooks or data imports/exports; and
- enabling `E2E_ENABLE_TENANCY`, `E2E_ENABLE_ORG_INVITATIONS` or
  `E2E_ENABLE_ORG_ONBOARDING` as release claims while their contracts are still
  skipped/placeholders.

Existing global coach authorization is not tenant isolation. Role checks,
unguessable IDs and friendly UI filtering cannot substitute for ownership
enforcement. If multiple coaches are evaluated before this gate passes, each
must use a separately isolated, approved deployment and data boundary; that is
an operational exception, not shared multi-coach readiness.

## In-bound features after all gates pass

- named coach and athlete accounts with least-privilege assignments;
- coach creation and maintenance of athlete profiles;
- powerlifting blocks, weeks, sessions and work-set prescriptions;
- explicit coach review before programme publication;
- athlete save/resume and completion of squat, bench and deadlift sessions;
- coach retrieval of completed training and weekly/nutrition check-ins;
- manual, source-linked coaching decisions and programme edits; and
- competition tooling only when the coaching owner has included it in the
  cohort protocol and separately smoke-tested it.

Recommendations remain advisory. They must never publish or mutate an athlete's
programme without an accountable coach's review.

## Out of scope for the beta

- unattended/public onboarding, open registration or viral invitations;
- bodybuilding, supplement advice, medical diagnosis or generic multi-sport use;
- automatic load changes, autonomous coaching or safety monitoring;
- guaranteed offline operation or native-app distribution;
- emergency, pain or injury response inside the product;
- official MyFitnessPal automation (the official API is disabled);
- promises of continuous availability, regional disaster recovery or a proven
  recovery time/objective without recorded evidence; and
- ad-hoc database edits as a user-support or completed-log correction workflow.

## Known limitations requiring participant acknowledgement

- Programme order is completion-based rather than a reliable training calendar;
  dated plans, missed sessions, travel and holidays need coach instructions.
- Training warm-up domain abstractions are not a shipped structured athlete
  workflow; the coach must verify clear warm-up and ramp instructions are visible.
- Completed training does not enter the main coach review queue. The coach must
  poll each athlete and use the agreed external completion channel.
- Completed session logs are locked and have no supported correction/revision
  workflow. Escalate mistakes; do not rewrite data directly.
- Messaging has no general thread, read receipt, urgent escalation or delivery
  guarantee. Safety and urgent communication use the external channel.
- Athlete self-service reset, account closure, complete export/deletion and
  consent/terms workflows are incomplete.
- Email invitation delivery, edge identity eligibility and the generated public
  hostname require environment-specific proof.
- Browser tests use disposable SQLite and synthetic accounts; they do not prove
  PostgreSQL, email, identity-provider or live-environment behavior.
- Tracked PostgreSQL configuration declares seven-day PITR, one application
  replica, no database HA and no geo-redundant backup. Restore/cutover is manual,
  and the repository contains no recorded database restore exercise or formal
  RPO/RTO.

Any participant requirement that conflicts with these limits is a NO-GO until
the product or operating model changes and is re-accepted.
