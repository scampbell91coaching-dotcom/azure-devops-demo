# Playwright release tests

This suite exercises the real Traditional Strength coach and athlete login,
session, role and CSRF flows against disposable deterministic users.

## Prerequisites

- Node.js 20+
- Python 3.12+
- Python packages from `platform-portal/requirements.txt`

Install and run:

```bash
python3 -m pip install -r platform-portal/requirements.txt
npm ci
npx playwright install chromium
E2E_TEST_ONLY=1 npm run e2e
```

Useful local commands:

```bash
npm run e2e:headed
npm run e2e:ui
npm run e2e:report
```

Playwright starts the portal on loopback port 8091. The launcher creates a
uniquely named SQLite database, removes it on shutdown, and inserts fixed IDs
and values. It never reads the normal local or production database. CI defaults
to one worker; local parallel workers are supported by the isolation rules below.

The explicit `E2E_TEST_ONLY=1` acknowledgement is mandatory. `E2E_BASE_URL` is
always rejected, shared/production environment markers are refused, an
unpredictable per-run token protects test-only hooks, and existing servers are
never reused.

Screenshots and traces are retained only for failed tests. The database contains
synthetic records only and temporary runner output is deleted after the run.

## Mutable-fixture isolation

Mutating specs declare a `mutationScope` through `e2e/fixtures/test.ts`. The
fixture takes a run-token-scoped filesystem lease for that workflow, so repeats
and retries cannot overlap while unrelated workflows can still run in parallel.

Each workflow resets only the records it owns through the disposable server's
`/__e2e/reset/<fixture>` endpoint. Reset names are allow-listed in
`e2e/support/seed_database.py`. The endpoint exists only in the E2E launcher,
requires the per-run header token and normal CSRF, and is absent from the
production application.

Fixture ownership is explicit:

- athlete 101 owns nutrition-import, training-completion/warm-up, and weekly
  check-in state under separate scopes;
- athlete 202 owns service-entitlement and check-in-setting scenarios and has a
  dedicated athlete login and active programme;
- athlete 303 owns the pilot invitation, publication, and completion money path;
- athlete 808 owns the standalone one-time invitation workflow.

## Future SaaS fixture contract

`e2e/fixtures/saas.ts` adds two deterministic logical organizations. Each has
an owner, a coach, and an athlete; the seed also provides distinct accounts for
multiple coaches. Owners intentionally use the current coach-compatible login
role because organization memberships do not exist yet. The logical tenant
labels are test metadata only and are not evidence of authorization.

Use `roleSession` or `roleRequestSession` for owner/coach/athlete sessions, and
`directIdIsolationProbe` for a list of cross-tenant direct-ID URLs. The probe
accepts only 403 or 404, with 404 preferred once tenant-qualified loading lands.

Future contracts are opt-in so the current release suite stays green:

- `E2E_ENABLE_TENANCY=1` enables direct-ID tenant isolation probes;
- `E2E_ENABLE_ORG_INVITATIONS=1` exposes the invitation placeholder;
- `E2E_ENABLE_ORG_ONBOARDING=1` exposes the onboarding placeholder.

The latter two placeholders are expected failures until their provider
adapters and product routes exist. They make no billing or email-provider calls.
Do not enable the tenancy flag until organization membership and tenant-scoped
queries are implemented; today's global coach role is intentionally not
represented as secure multi-tenant behavior.

For a new mutating workflow, prefer a dedicated athlete. Otherwise add a narrow,
idempotent reset, prove an unrelated athlete is unchanged, and use a matching
mutation scope. Never add an E2E reset route to a production blueprint.
