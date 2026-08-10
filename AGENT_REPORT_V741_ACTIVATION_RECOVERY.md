# Agent B report: V7.4.1 activation recovery hotfix

## Outcome

The athlete invitation form now treats mismatched passwords as a recoverable validation error. The response keeps the still-valid invitation token in the hidden form field, and the browser code accepts that server-preserved context after the original URL fragment has been removed. The password fields and submit button therefore remain editable for correction.

Token lifecycle semantics are unchanged. A mismatch never calls `consume_token`; successful activation still uses the existing atomic conditional consume and activates the athlete once; expired, revoked, invalid, and replayed links still render the unavailable state and return HTTP 410.

## Changes

- `platform-portal/portal/auth.py`: return an available submitted token to the validation-error render only; unavailable tokens are never returned to an editable form, and account-token responses are marked `no-store`.
- `platform-portal/templates/auth/set_password.html`: populate the hidden token field from that validated render context.
- `platform-portal/static/js/account_token.js`: allow an already-populated, correctly shaped hidden token on a fragment-free validation response.
- `platform-portal/tests/test_account_lifecycle.py`: cover mismatch, unchanged token/user state, correction, single consumption, and rejected replay.
- `e2e/tests/auth.spec.ts`: extend the invitation browser journey through mismatch, editable correction, activation, and replay rejection.

No migrations, infrastructure, GitOps, production changes, or merge were performed.

## Verification

- `pytest -q platform-portal/tests/test_account_lifecycle.py` — 10 passed.
- `pytest -q platform-portal/tests/test_auth.py platform-portal/tests/test_account_lifecycle.py platform-portal/tests/test_athlete_dashboard.py` — 66 passed.
- `npx playwright test e2e/tests/auth.spec.ts` — not run: Playwright is not installed in this checkout and the restricted environment could not resolve `registry.npmjs.org` (`EAI_AGAIN`) when `npx` attempted to download it.
- `git diff --check` — passed.

## Residual verification

Run `npx playwright test e2e/tests/auth.spec.ts` in the normal dependency-provisioned E2E environment. The committed browser scenario contains the complete required mismatch → correction → activation → replay-rejected flow.
