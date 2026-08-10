# V7.9 Security and Authorization report

## Outcome

Audited the portal's authentication, role, athlete ownership, CSRF, service
entitlement, history-locking, and proposal-integrity patterns for the new
coaching delivery workflows.

The audit found and fixed one active authorization gap: nutrition import
preview, commit, and disconnect were athlete-allowlisted. They are now
coach-only mutations. Athletes retain access to their own import summary and
receive `404` for another athlete's summary.

## Deliverables

- Added `platform-portal/docs/v7.9-security-authorization-matrix.md` with the
  operation-by-operation role, ownership, entitlement, history, CSRF, and
  response-code contract.
- Added `platform-portal/tests/test_v79_authorization_boundaries.py` covering
  coach-only nutrition import, warmup, and Block Factory mutations; owned and
  cross-athlete nutrition reads; and CSRF rejection across delivery mutations.
- Narrowed `portal.auth._ATHLETE_ENDPOINTS` so an authenticated athlete cannot
  preview, commit, or disconnect a nutrition import.

## Audit notes

- Macro prescriptions and meal plans currently have domain services but no
  persistence-backed delivery routes. Warmup recommendations have no dedicated
  accept/reject routes. The matrix defines required coverage before those
  surfaces ship.
- Warmup assignment ownership is derived through the persisted session/block
  graph and athlete reads are owner-checked. First read snapshots history and
  later mutation returns `409`.
- Block Factory proposal acceptance derives athlete identity from the stored
  proposal, verifies keyed integrity, recomputes source state, and atomically
  prevents replay.
- Nutrition import already enforces nutrition entitlement and scopes import jobs
  by athlete. Service changes are explicitly coach-decorated.
- Training entitlement is not yet enforced on the legacy programming, warmup,
  and Block Factory routes. This is recorded as a required guard for new/current
  V7.9 delivery actions; historical reads must remain accessible according to
  product policy.
- The current data model has no coach-to-athlete tenant ownership relation. The
  matrix therefore documents current “any authenticated coach” behavior without
  redesigning authentication or inventing a false ownership boundary.

## Verification

`pytest -q tests/test_v79_authorization_boundaries.py tests/test_nutrition_import.py tests/test_auth.py tests/test_warmup_integration.py tests/test_block_factory_v3.py`

Result: **92 passed**.

Full portal regression: `pytest -q` — **500 passed, 2 skipped**.

## Commit status

Commit creation was attempted with message
`test(security): define V7.9 delivery authorization boundaries`, but the managed
workspace exposes the linked Git worktree metadata read-only. Git could not
create `.git/worktrees/v79-security-authz-20260810-221810/index.lock`. All scoped
changes remain present and unstaged in this worktree for the orchestrator to
commit.
