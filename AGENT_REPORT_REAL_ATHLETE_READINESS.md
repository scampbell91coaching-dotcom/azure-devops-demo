# Agent D — V7.3 real-athlete-readiness report

## Outcome

The full audit is in [`docs/v7.3-real-athlete-readiness.md`](docs/v7.3-real-athlete-readiness.md).

**Verdict: no-go for unattended onboarding of an arbitrary athlete tomorrow.** A supervised exception is possible only after proving that exact athlete can pass the production Entra/OAuth2 edge and Flask login, then operating manual controls for invitation delivery, programme dates, warm-ups, completed-session review and messaging.

## Highest-risk confirmed findings

1. The production private ingress requires Entra/OAuth2 before the application's separate athlete login. Athlete access is therefore not established by the new account lifecycle alone.
2. Invitation/reset code is robust, but the production manifest does not declare SMTP or `ACCOUNT_PUBLIC_BASE_URL`; manual one-time-link delivery is the evidenced fallback.
3. Programme “current week” is the first unfinished session. Blocks have no dates and no holiday/travel exception model.
4. The V7.2 warm-up service is domain-only: no persistence adapter, route, form, template or athlete-session integration exists.
5. Completed session logs do not enter the coach review queue. There is no general messaging, notification, unread state or urgent escalation channel.
6. Athlete export/closure/deletion and completed-log correction do not exist. PostgreSQL PITR is declared, but restore is manual and untested; production declares one replica.
7. Infrastructure and intelligence foundations are materially more developed than the actual issue-to-intervention and coach-review loops.

## Priority recommendation

- **P0:** prove edge/auth and invitation on the deployed journey; publish a dated schedule and warm-ups via explicit temporary notes; institute daily completed-log review and an external urgent channel; record one production journey smoke test.
- **P1 beta:** calendar/exceptions, warm-up UI/persistence, unified completed-session/check-in review, issue-to-intervention with diff/outcome, programme revisions, intake confirmation, practical messaging, lifecycle/export and operational error visibility.
- **P2 SaaS:** tenancy, billing, configurable policy/taxonomy, queue/scale work, formal commercial retention/DR and learned automation.

Spreadsheet-parity statements are separated as hypotheses because no representative coaching spreadsheet is present. The audit recommends observing one real setup, training review, weekly review and schedule disruption before expanding schemas or rule catalogues.

## Scope and verification

- Documentation/audit only; no migrations, application implementation, CI/CD, production configuration or merge.
- Full portal test command: `python -m pytest -q` — **426 passed, 2 skipped in 42.22s**.
- `git diff --check` should be run immediately before handoff.
