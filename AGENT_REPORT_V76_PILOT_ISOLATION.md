# Agent B Report — V7.6 Pilot E2E Isolation

## Outcome

The first-paying-athlete scenario now resets Taylor Jordan's dedicated mutable
fixture state before every Playwright attempt. Playwright retries reuse the E2E
server/database, but each attempt invokes a token-protected, authenticated,
test-only reset route before asserting that the athlete is `Not Invited`.

No production route, migration, or product assertion was changed.

## Implementation

- Added `reset_pilot_fixture()` to `e2e/support/seed_database.py`.
- Scoped reset targets to pilot athlete `303`, pilot block `601`, and pilot
  session `801`.
- Reset account lifecycle by deleting Taylor's account tokens and athlete user,
  including active/password state.
- Restored pilot block status to `draft`.
- Deleted pilot-session logs and set results.
- Deleted pilot-session warm-up snapshots, snapshot steps, overrides, and
  assignments.
- Deleted dedicated-pilot weekly/nutrition check-ins and check-in settings.
- Added `POST /__e2e/reset/pilot` only to the disposable E2E server launcher.
  It requires the per-run E2E token, normal coach authentication, and CSRF.
- Added a Playwright `beforeEach` reset so initial attempts and retry #1/#2 use
  the same clean boundary.
- Preserved the `Not Invited`, publication, immutable completed-log, and coach
  review-queue assertions.

## Focused reset test

`platform-portal/tests/test_e2e_pilot_reset.py` mutates every reset category,
calls the reset twice to prove idempotence, and verifies an unrelated athlete's
user, active block, training log, and set result remain unchanged.

## Verification

- `pytest -q platform-portal/tests/test_e2e_pilot_reset.py`
  - `1 passed`
- `pytest -q platform-portal/tests`
  - `468 passed, 2 skipped`
- `git diff --check`
  - passed
- Repository-wide `pytest -q`
  - collection blocked by the pre-existing root test import layout:
    `tests/test_app.py` cannot import `app.app` because `app` resolves as a
    non-package in that invocation. The complete platform-portal suite above
    passed.
- Focused Playwright with `--retries=2 --repeat-each=3`
  - unavailable in this checkout: `node_modules/.bin/playwright` is absent and
    `npx` cannot download it because npm DNS/network access is restricted
    (`EAI_AGAIN registry.npmjs.org`). Full Playwright was therefore also not
    available.

## Scope

Changes are limited to E2E support, the pilot E2E spec, a focused Python test,
and this report. No merge was performed.
