# Agent B report: V7.4 auth and invitation readiness

## Outcome

Implemented the smallest security-preserving onboarding improvement and deterministic evidence around the first athlete journey. No database migration, Azure/Kubernetes/GitOps change, security relaxation, or merge was performed.

The application invitation lifecycle is pilot-ready; the deployed journey is not proven until the selected athlete passes the Entra edge and confirms actual receipt.

## Findings

- Production nginx applies OAuth2 Proxy external auth to `/`, so invitation, activation, login and athlete pages all require an Entra-accepted identity first.
- Flask then independently checks email/password, active state, eight-hour session age, role and athlete ownership.
- The boundary is both expected infrastructure defence-in-depth and an athlete product defect: it fits an internal private portal but external-athlete edge eligibility has no documented/proven identity contract.
- Replacing Flask authentication with `X-Auth-Request-Email` would be unsafe without a cryptographically bound trusted-proxy contract and direct-origin protections. This work does not do that.
- Invitation tokens are high entropy, digest-only at rest, purpose-bound, expiring, revocable, single-use and atomically consumed. Fragments keep raw tokens out of HTTP requests/referrers and client JavaScript removes them from the address bar.
- Account activation creates the Flask session and already avoided another immediate password prompt. It now lands with an explicit activation confirmation.
- Production manifests reviewed in this work do not declare SMTP variables or `ACCOUNT_PUBLIC_BASE_URL`. SMTP `sent` means provider acceptance, not inbox delivery. The manual fallback is viable when handled as a secret.

## Changes

- Added optional edge-identity email prefill and a clear “continue with your Traditional Strength password” notice. The header never authenticates, selects authorization, or skips the password check.
- Added explicit activation and password-update landing states on the athlete dashboard.
- Added `flask --app app account-delivery-readiness`, which reports readiness without revealing hostnames, usernames, passwords, tokens, recipients or bodies.
- Strengthened unit/integration coverage for edge prefill without trust, safe athlete login redirect, delivery-readiness redaction, and first-login landing.
- Updated browser invitation coverage to assert the activation landing.
- Added the exact journey, defect classification, evidence boundary and one-athlete pilot runbook in `docs/v7.4-athlete-onboarding-flow.md`.

## Verification

Focused command:

```text
cd platform-portal
pytest -q tests/test_auth.py tests/test_account_lifecycle.py
57 passed
```

Full portal command:

```text
cd platform-portal
pytest -q
458 passed, 2 skipped
```

`git diff --check` passed. The focused Playwright auth spec was not executable in this workspace because `node_modules` was absent and restricted network access prevented `npx` from fetching Playwright (`EAI_AGAIN`). The browser assertion was updated, but it still requires execution in the normal dependency-provisioned E2E environment.

The existing lifecycle cases deterministically cover invitation validity, expiration, replay, revocation/reissue, account activation and password reset. The focused suite also covers login redirect and delivery configuration redaction.

## Remaining risks / go-live gate

1. Prove the exact athlete’s Entra eligibility before sending the invitation.
2. Set and verify the canonical production `ACCOUNT_PUBLIC_BASE_URL` through the existing deployment process; no manifest was changed here.
3. Prove one real inbox delivery or execute the trusted manual fallback. Provider acceptance alone is insufficient.
4. Capture token-free evidence of edge pass, receipt, activation, replay rejection, logout/login and athlete dashboard landing.
5. A future single-sign-on design needs an explicit identity mapping and trusted-header/origin contract. It should not be inferred from the current forwarded email header.

Do not describe general athlete onboarding as resolved until those deployed checks pass.
