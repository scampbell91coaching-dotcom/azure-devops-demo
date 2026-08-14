# V7.15 blocker handoff: canonical data integrity and bootstrap tooling

## Commit SHA

Unavailable in this execution environment. `git commit` was attempted after
the implementation and tests passed, but Git could not create
`/home/steve/azure-devops-demo/.git/worktrees/data-integrity-bootstrap/index.lock`
because the shared worktree metadata is mounted read-only. The implementation
was not committed; an operator with a writable Git metadata mount must commit
the listed files.

## Summary

Added `flask --app app reconcile-canonical-tenancy`, a conservative,
idempotent operational reconciliation command. It defaults to a read-only JSON
dry run and requires `--apply` for mutation. It supports only the unambiguous
single-active-organisation/single-active-coach legacy bootstrap, creating a
missing owner membership and missing athlete ownership rows atomically.

The tool refuses with actionable output for absent or ambiguous organisation
scope, ambiguous coach identity, inactive lifecycle rows, and inconsistent
existing ownership. It never chooses by lowest ID, email, name, or another
heuristic and never reactivates an inactive record.

## Files changed

- `platform-portal/portal/services/canonical_tenancy_reconciliation.py`
- `platform-portal/portal/database_cli.py`
- `platform-portal/tests/test_canonical_tenancy_reconciliation.py`
- `platform-portal/docs/canonical-tenancy-reconciliation.md`
- `V715_BLOCKER_HANDOFF.md`

## Tests run and results

- `pytest -q tests/test_canonical_tenancy_reconciliation.py`: 10 passed.
- `pytest -q tests/test_canonical_tenancy_reconciliation.py tests/test_tenancy.py tests/test_organisation_domain.py tests/test_cross_tenant_security.py tests/test_security_assurance.py`: 49 passed.
- `git diff --check`: passed before handoff creation; rerun during final verification.

Tests cover no organisation, missing membership, missing ownership, healthy
state, ambiguous multi-organisation state, inactive membership, inactive
ownership, dry-run default, explicit apply, and repeated-run idempotency.

## Security and tenancy impact

Authorization controls are unchanged and not weakened. The repair is fail
closed outside the single-tenant/single-coach case. It adds only canonical
membership and ownership rows that make legacy athlete data accessible to the
sole active coach in the sole active organisation. Existing inactive lifecycle
decisions are preserved. No external service or production environment was
accessed.

## Migration impact

None. There is no schema migration and no `alembic_version` access or mutation.

## Unresolved risks

- The changes are uncommitted solely because Git metadata is read-only in this
  environment. The working tree therefore cannot be left clean here.
- Ambiguous installations require an authorised operator to establish explicit
  tenant assignments through the approved business process; the tool
  intentionally cannot resolve them.
- The command was tested only against disposable in-memory SQLite databases in
  this task and was not run against production.

## Integration notes

Review the dry-run JSON before every apply. After applying, rerun without
`--apply` and require `status: healthy`. Retain both reports with the approved
change record. Do not bypass a refusal, rewrite inactive states, or manually
edit `alembic_version`.

To finish integration in a workspace with writable Git metadata:

1. Review `git diff` and rerun the tests above plus `git diff --check`.
2. Commit all five listed files on the existing feature branch.
3. Confirm `git status --short` is empty. Do not merge, rebase, push, or deploy
   as part of this tranche.
