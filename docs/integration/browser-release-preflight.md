# Browser and release preflight

Date: 2026-08-13. Scope: integrated branch snapshot and local disposable resources only.

## Status

**Code preflight is prepared; browser execution is blocked in this runner by environment capabilities.** Future tenancy probes are not marked green because Chromium and loopback socket startup were unavailable here.

| Area | Status | Evidence / action |
|---|---|---|
| Playwright package | Ready | `npm ci --ignore-scripts` installed `@playwright/test` 1.62.1; `E2E_TEST_ONLY=1 npx playwright test --list` discovered 75 tests in 15 files. |
| Chromium runtime | Environment blocker | Playwright Chromium v1234 is not installed. Install with `npx playwright install chromium` in a browser-capable verification runner. |
| Local web servers | Environment blocker | This sandbox rejects loopback socket creation with `PermissionError: [Errno 1] Operation not permitted`. This is not an application response or test failure. |
| Two-Organisation seed | Ready | The disposable SQLite seed now creates two canonical `Organisation` rows, four owner/coach `OrganisationMembership` rows, and two `CoachAthleteOwnership` rows. Its repeat-safe test passes. No alternative tenant model was added. |
| Authentication/session | Ready by focused checks | E2E starts with `AUTHENTICATION_DISABLED=False`, a per-run random secret, HTTP-only SameSite=Lax session cookies (Secure disabled only under Flask testing), and real coach/athlete password hashes. |
| CSRF | Ready by focused checks | Login obtains a session CSRF token and mutation fixtures submit it. Reset hooks require the unpredictable run-token header plus normal CSRF, are loopback/test-only, and are absent from the production app. |
| Migration head | Ready locally | `python3 -m alembic -c migrations/alembic.ini heads` reports the single head `0023_organisation_invitation_delivery`. Release evidence and the read-only tenancy verifier now expect 0023. |
| PostgreSQL migration verification | Environment-only pending | No `POSTGRES_TEST_DATABASE_URL` is configured. The verifier CLI is loadable and its unit contracts pass; an actual expand/backfill/constrain check requires a disposable PostgreSQL database, never a live database. |
| Release evidence command | Partially ready | `scripts/release/release-evidence --repo-root "$PWD"` is correctly wired and non-deploying. In this runner its mandatory Ruff check will fail because `ruff` is missing; Helm v3.21.3 and Terraform v1.15.8 are present. The optional PostgreSQL check will be skipped while its URL is unset. |

## Required invocation and prerequisites

Use Node 20+ and Python 3.12+, install `platform-portal/requirements.txt`, run `npm ci`, and install Chromium. Run only against the launcher-owned SQLite database:

```sh
npm ci
npx playwright install chromium
E2E_TEST_ONLY=1 npm run e2e
```

Do not set `E2E_BASE_URL`. The configuration rejects it, requires the explicit test-only acknowledgement, generates a per-run token, places the SQLite file below repository `.tmp`, and refuses production/staging/shared environment markers.

## Ordered smoke verification

Run in this order so boundary failures stop deeper workflow verification:

1. Preflight discovery: `E2E_TEST_ONLY=1 npx playwright test --list`.
2. Public/health boundary: `E2E_TEST_ONLY=1 npx playwright test e2e/tests/public.spec.ts --project=chromium`.
3. Authentication, logout, role denial, CSRF and account activation: `E2E_TEST_ONLY=1 npx playwright test e2e/tests/auth.spec.ts --project=chromium`.
4. Tenant isolation, with no invitation/onboarding placeholder flags: `E2E_TEST_ONLY=1 E2E_ENABLE_TENANCY=1 npx playwright test e2e/tests/saas-tenancy.future.spec.ts --project=chromium`. Both direct-ID tests must actually pass before tenancy is called green.
5. Coach roster and programming: `E2E_TEST_ONLY=1 npx playwright test e2e/tests/coach.spec.ts --project=chromium`.
6. Athlete training and service entitlements: `E2E_TEST_ONLY=1 npx playwright test e2e/tests/athlete-training.spec.ts e2e/tests/athlete-services.spec.ts --project=chromium`.
7. Nutrition and meal plan: `E2E_TEST_ONLY=1 npx playwright test e2e/tests/nutrition-import.spec.ts e2e/tests/meal-plan.spec.ts --project=chromium`.
8. Performance and money path: `E2E_TEST_ONLY=1 npx playwright test e2e/tests/performance-dashboard.spec.ts e2e/tests/pilot-money-path.spec.ts --project=chromium`.
9. Mobile/UI assurance: `E2E_TEST_ONLY=1 npx playwright test --project=mobile-chromium` followed by `coach-desktop-ux.spec.ts` on Chromium.
10. Full browser suite: `E2E_TEST_ONLY=1 npm run e2e`.

Organisation invitation and onboarding cases remain explicit expected-failure placeholders. Do not enable `E2E_ENABLE_ORG_INVITATIONS` or `E2E_ENABLE_ORG_ONBOARDING` as release-green evidence.

## Release and migration evidence

After browser smoke passes in the capable runner:

```sh
scripts/release/release-evidence --repo-root "$PWD"
python3 scripts/migrations/saas_tenancy_verify.py \
  --database-url "$DISPOSABLE_POSTGRES_URL" --phase expand
python3 scripts/migrations/saas_tenancy_verify.py \
  --database-url "$DISPOSABLE_POSTGRES_URL" --phase backfill
python3 scripts/migrations/saas_tenancy_verify.py \
  --database-url "$DISPOSABLE_POSTGRES_URL" --phase constrain
```

The migration verifier opens a read-only transaction, checks exactly one expected head through 0023, validates canonical control tables and removed schema families, and performs progressively stronger ownership and constraint checks. Point it only at an authorized disposable verification database.

## Failure classification

- Environment-only here: missing Chromium, forbidden loopback sockets, missing Ruff, and absent disposable PostgreSQL URL.
- Code defects corrected: stale 0022 expectations in both evidence commands; E2E tenant identities previously lacked persisted canonical Organisation membership/ownership rows.
- Not yet proved: browser tenant direct-ID isolation and the full 75-test Playwright run. Any 200 response in the enabled cross-tenant probes is a code/security defect, not a fixture exception.
- Known integrated Python failures (reported before this preflight) still require their own cluster triage; this report does not relabel the reported 25 failures or future tenancy checks as green.
