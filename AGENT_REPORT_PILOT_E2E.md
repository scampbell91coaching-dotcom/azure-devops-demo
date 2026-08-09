# Agent E — V7.4 supervised-pilot E2E report

## Outcome

A production-like browser scenario now represents the narrowest supervised journey for one athlete: coach-issued manual invitation, one-time activation, empty pre-publish state, coach publication, athlete next-session visibility, coach-authored warm-up notes, mobile work logging, finish/lock, reload persistence, cross-athlete authorization checks, and coach retrieval of the completed log.

The operational checklist is in [`docs/v7.4-supervised-pilot-runbook.md`](docs/v7.4-supervised-pilot-runbook.md).

**Verdict:** a single-athlete pilot remains possible only as a supervised exception. There is one confirmed product P0 in the required journey: a completed training session does **not** appear in the coach's “Athletes requiring review” queue. The E2E keeps this limitation executable and proves the documented fallback—external completion signal plus same-day polling of the athlete's Completed sessions list—but does not misrepresent that fallback as queue coverage.

## Changes

### Focused E2E path

`e2e/tests/pilot-money-path.spec.ts` extends the existing paying-athlete path rather than adding a duplicate test. It now covers:

- the supported coach invitation UI and non-email manual-link fallback;
- password creation through the real one-time activation page;
- athlete dashboard before programme publication;
- direct cross-athlete session access returning 404;
- athlete access to coach-only athlete data returning 403;
- draft review, publication, and publication persistence;
- dashboard “Next session” identity;
- visible coach-authored warm-up/ramp and urgent-channel notes;
- 390×844 mobile rendering, five set results, and a set note;
- completion, immutable display, and result persistence after reload;
- explicit evidence that Taylor is absent from the coach action queue;
- the supervised coach fallback and exact submitted-result review;
- absence of the other seeded athletes on athlete/result views.

`e2e/support/seed_database.py` is changed only as a browser-test helper: Taylor is no longer pre-provisioned with a login, forcing the scenario through account activation, and the pilot session contains the temporary warm-up contract recommended by the readiness audit. There are no migrations or production-data changes.

The existing focused invitation test in `e2e/tests/auth.spec.ts` remains useful for single-use-token replay behavior. The pilot scenario does not duplicate the replay assertion.

## Isolation evidence and limit

The browser path explicitly verifies user/athlete isolation at both resource and role boundaries: a logged-in Taylor receives 404 for Alex's known session and 403 for a coach-only athlete page; athlete-visible and reviewed-result pages are checked for seeded other-athlete names.

True tenant isolation cannot be asserted because the current data model and runtime have no tenant identifier or second tenant. The test therefore names and verifies the isolation boundary that exists rather than implying multi-tenant support. This does not block a one-coach/one-athlete supervised pilot, but it must block any claim of multi-tenant readiness.

## Remaining P0 defects and operational gates

### Confirmed product P0

**Completed training is missing from the coach review queue.** `CoachDashboardService._reviews` builds items only from weekly and nutrition check-ins. There is also no reviewed/unreviewed state for training logs. A clear dashboard queue can therefore coexist with an unseen completed session.

This should block a real athlete unless all of the following containment is accepted: one external completion/urgent channel, coach availability, same-day athlete-page polling, and a recorded daily review checklist. It should block expansion beyond the tightly supervised pilot. The durable fix is a completed-session review item with unseen/reviewed state and a direct link to the exact immutable log—not an everlasting list of every historical completion.

### Production gates still requiring live evidence

- The exact athlete must prove passage through the Entra/OAuth2 edge and the separate Flask login in a clean browser.
- Invitation hostname and delivery must be checked through production. Repository manifests previously did not evidence SMTP or `ACCOUNT_PUBLIC_BASE_URL`; the manual link is containment, not delivery readiness.
- The dated schedule and per-session warm-up remain notes-based because calendar and training warm-up UI/persistence are absent.
- Live PostgreSQL write/reload, production logs, backup availability, and rollback ownership require operational verification. Disposable SQLite browser evidence cannot prove them.

Failure of edge/account access, authorization isolation, correct session/warm-up visibility, save/reload persistence, or same-day coach retrieval is a hard no-go for the athlete.

## Verification

- Attempted: `E2E_TEST_ONLY=1 npx playwright test e2e/tests/pilot-money-path.spec.ts`
- Result: **not run**. This checkout has no installed Playwright package; `npx` attempted `https://registry.npmjs.org/playwright` and failed with restricted-network `EAI_AGAIN`. No browser result is claimed.
- `python -m pytest -q tests/test_e2e_seed_database.py tests/test_e2e_security.py`: **8 passed, 1 failed**. The failure is stale baseline expectation in `test_fresh_e2e_database_seeds_once_and_safe_repeat_is_idempotent`: it expects 10 exercises/two athletes, while the pre-existing seed already includes `Pause Squat` and Taylor (11/three). The failure occurs on the exercise set before the athlete-count assertion. This change did not introduce either fixture.
- `git diff --check`: **passed**.
- Required before handoff/deployment in a prepared environment: `npm ci`, `npx playwright install chromium`, then `E2E_TEST_ONLY=1 npx playwright test e2e/tests/pilot-money-path.spec.ts`.
- No migration, infrastructure, or merge action was performed.

## Recommendation

Run the focused scenario in the normal prepared E2E environment, then execute the runbook with a synthetic production identity before involving the real athlete. Proceed with one athlete only if every live gate passes and the coach explicitly accepts manual completion polling. Prioritize a reviewed/unreviewed completed-training queue immediately; until it exists, unattended onboarding remains no-go.
