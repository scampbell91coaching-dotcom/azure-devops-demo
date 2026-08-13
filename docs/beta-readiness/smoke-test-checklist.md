# Coach and athlete smoke test

Run with synthetic accounts first. Use a unique run ID and a disposable,
clearly labelled powerlifting block. Record pass/fail, UTC time, release ID,
role, supported device/browser and sanitized correlation IDs. Never retain
passwords, tokens or athlete health data.

## Tenant and identity guardrail

- [ ] Tenant A owner/coach and athlete A can sign in; tenant B equivalents can
  sign in; sign-out invalidates the expected session.
- [ ] Each coach list/search contains only their tenant's approved athletes.
- [ ] Tenant B coach cannot read or mutate tenant A athlete, block, session,
  result, check-in or report by direct ID; repeat in the opposite direction.
- [ ] Athlete A cannot open coach pages or athlete B resources; failures return
  403/404 without revealing names, counts, state or timing-sensitive detail.
- [ ] Invitation/reset token is tenant-bound, single-use, expiring and revocable;
  wrong-tenant/wrong-recipient use fails without creating an account link.

**Stop immediately on any cross-tenant or cross-athlete exposure.** Do not
continue merely to collect more examples.

## Coach powerlifting path

- [ ] Create a synthetic athlete with federation, weight class/bodyweight and
  competition context; verify the athlete appears only in the intended roster.
- [ ] Create a draft block containing ordered squat, bench press and deadlift
  sessions with work sets, target load/reps/RPE, exercise notes and explicit
  warm-up/ramp instructions in the delivered surface.
- [ ] Review prescription values and order, publish the block, and confirm a
  previous active block behaves as expected.
- [ ] Confirm athlete dashboard and coach agree on the intended next session;
  reconcile completion-based ordering with the dated external plan.
- [ ] After athlete completion, manually open the athlete's Completed sessions,
  verify prescription snapshot, actual load/reps/RPE, skipped/completed state
  and notes, then record review externally.
- [ ] Open and respond to a weekly check-in; confirm the response is visible only
  to the intended athlete.

## Athlete powerlifting path

- [ ] Activate the invitation, sign out/in, and verify only the assigned active
  block and personal data are visible.
- [ ] On the actual supported phone, open the intended session; verify squat,
  bench or deadlift prescription, order, notes and warm-up are readable with no
  blocked controls or horizontal overflow.
- [ ] Enter actual load, reps and RPE for a work set, mark completed/skipped as
  appropriate, add a benign note, save progress, reload and verify persistence.
- [ ] Resume, complete remaining work sets, select Finish session once and see
  completion confirmation.
- [ ] Reload and verify the completed prescription/results persist and inputs are
  locked. Do not test correction with a direct database edit.
- [ ] Submit the agreed weekly check-in and confirm the coach response appears
  only in this athlete account.

## Operational and negative checks

- [ ] Authenticated read and disposable write/reload pass through the deployed
  edge and PostgreSQL; `/health` alone is insufficient.
- [ ] Refresh, back button and double-submit do not duplicate completion or move
  data to another session/athlete.
- [ ] Expected validation errors preserve valid entered data and reveal no stack
  trace, credential, token or another participant's information.
- [ ] Coach receives the external completion signal and retrieves the completed
  log within the agreed response time; do not rely on the review queue.
- [ ] Sanitized logs show no unexplained authentication, CSRF, 5xx or database
  errors for the run.
- [ ] Synthetic records are retired using an approved supported process; do not
  improvise deletion against a live database.
