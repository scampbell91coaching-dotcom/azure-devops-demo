# Playwright release tests

This suite covers only Traditional Strength workflows currently present in the
Flask portal. It does not claim to test authentication: application login has
not landed. `authenticatedState` in `e2e/fixtures/test.ts` is an intentionally
empty seam for a future Playwright `storageState` login fixture.
The runner exposes a test-only athlete-session selector so isolation can be
checked without pretending that selector is authentication coverage.

## Prerequisites

- Node.js 20+
- Python 3.12+
- Python packages from `platform-portal/requirements.txt`

Install and run:

```bash
python3 -m pip install -r platform-portal/requirements.txt
npm ci
npx playwright install chromium
npm run e2e
```

Useful local commands:

```bash
npm run e2e:headed
npm run e2e:ui
npm run e2e:report
```

By default Playwright starts the portal on port 8091. The launcher deletes and
recreates `.tmp/traditional-strength-e2e.sqlite`, then inserts fixed IDs and
values. It never reads the normal local or production database. Tests run with
one worker because supported form submissions mutate this disposable database.

To test an already-running disposable environment, set `E2E_BASE_URL`. The
operator is responsible for ensuring that URL is isolated and contains the
documented fixture records; never point browser tests at production.

Screenshots and traces are retained only for failures in `test-results/` and
the HTML report is written to `playwright-report/`.
