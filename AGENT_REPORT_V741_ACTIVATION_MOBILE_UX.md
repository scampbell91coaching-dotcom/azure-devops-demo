# V7.4.1 Activation Mobile UX Hotfix

## Outcome

The athlete activation/password-reset page now has activation-scoped responsive styling. The existing login and access-denied layouts retain their shared styling and markup.

## Changes

- Constrained the 1170×1675 logo to a proportionate 64–88px rendered height.
- Centered and bounded the activation card on desktop, with 16px mobile gutters and 24px card padding below 760px.
- Styled password inputs at 16px with full-width, 50px-high controls to keep them readable/editable and avoid iOS input-focus zoom where supported.
- Added a full-width mobile CTA with a 48px minimum height.
- Added `overflow-wrap: anywhere` to activation errors and kept alert semantics intact.
- Added Playwright assertions to the real one-time invitation journey at 320, 390, and 430px for horizontal overflow, logo size, editable/password font sizing, CTA tap height, and the validation-error state before successful activation and replay rejection.

No authentication flow, token handling, JavaScript, CSP, persistence, infrastructure, or production configuration changed.

## Verification

- `python -m pytest platform-portal/tests/test_account_lifecycle.py platform-portal/tests/test_auth.py -q`
  - **Passed:** 57 tests.
- `git diff --check`
  - **Passed.**
- `E2E_TEST_ONLY=1 npx playwright test e2e/tests/auth.spec.ts --project=chromium --grep "manual invitation and athlete activates once"`
  - **Not executed in this workspace:** `node_modules` is absent and npm package retrieval was unavailable (`EAI_AGAIN registry.npmjs.org`). Run this command in the normal dependency-provisioned E2E environment.
