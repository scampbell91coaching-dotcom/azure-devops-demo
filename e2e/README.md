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
and values. It never reads the normal local or production database. Tests run with
one worker because supported form submissions mutate this disposable database.

The explicit `E2E_TEST_ONLY=1` acknowledgement is mandatory. `E2E_BASE_URL` is
always rejected, shared/production environment markers are refused, an
unpredictable per-run token protects test-only hooks, and existing servers are
never reused.

Screenshots and traces are retained only for failed tests. The database contains
synthetic records only and temporary runner output is deleted after the run.
