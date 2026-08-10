# V7.9 E2E Isolation Agent Report

## Outcome

Playwright's mutable workflows now have explicit ownership, deterministic
test-only resets, and run-scoped mutation leases. Retries and `--repeat-each`
start from the same scoped state, while unrelated mutation scopes remain able to
run on parallel workers.

## Audit and implementation

- Athlete 101 remains the primary read fixture. Its nutrition imports, training
  completion/warm-up records, and weekly check-in submissions now use separate,
  allow-listed resets.
- Athlete 202 is now dedicated to client-service entitlement and check-in-setting
  mutation. It has its own athlete account and minimal active programme, so those
  tests no longer disable nutrition while athlete 101 import tests are running.
- Athlete 303 remains dedicated to the pilot money path. Its existing reset was
  expanded to share complete training-state cleanup, including reusable warm-up
  protocol records, while restoring draft publication and invitation state.
- Athlete 808 is a new invitation-only fixture. Standalone activation tests no
  longer consume athlete 202's account state.
- Mutating spec files declare a `mutationScope`. A filesystem lease containing
  the unpredictable E2E run token prevents two repeats/retries of the same scope
  from overlapping. Different scopes do not share a lock.
- The reset helper authenticates as the deterministic coach and supplies normal
  CSRF. Reset routes still require the per-run `X-E2E-Run-Token` header.

## Security boundaries

- No production route or blueprint was changed.
- Reset routes are registered only by `e2e/support/run_server.py` after the
  disposable-environment checks and seed setup.
- Reset names are an explicit allow-list; unknown names return 404.
- Header-token comparison remains constant-time, and CSRF protection was not
  bypassed.
- Existing coverage proves the production application has no `/__e2e` route and
  rejects missing flags, short/missing tokens, shared environment markers, and
  unsafe database locations.

## Regression coverage

`tests/test_e2e_seed_database.py` now verifies:

- repeated seeding is idempotent with all four fixture athletes;
- a service reset can run twice safely;
- service changes and check-in settings return to baseline;
- athlete 101's identity/bodyweight remain unchanged by athlete 202's reset.

The mutating browser specs reset immediately before their workflows, including
nutrition import, invitation, training completion, weekly check-in, services,
and pilot publication/completion.

## Verification

```text
Focused E2E seed/security tests: 10 passed
Full platform-portal suite:       489 passed, 2 skipped
Playwright compile/discovery:     59 tests listed
git diff --check:                 passed
```

Focused and full browser execution were attempted after installing the locked
Node dependencies. The sandbox refused Werkzeug's loopback socket creation with
`PermissionError: [Errno 1] Operation not permitted`, so Playwright could not
start its disposable web server. The root-level `pytest -q` command was also
attempted; collection stopped on the repository's unrelated `app.app` package
shadowing error. The portal suite and focused E2E support suite both completed.

## Files

- `e2e/fixtures/test.ts`: mutation leases, reset client, and athlete 202 login.
- `e2e/support/seed_database.py`: dedicated fixtures and scoped idempotent reset
  implementations.
- `e2e/support/run_server.py`: guarded allow-listed reset dispatch.
- `e2e/tests/*.spec.ts`: mutation ownership and reset setup.
- `e2e/README.md`: contributor rules and fixture ownership.
- `tests/test_e2e_seed_database.py`: idempotence and unrelated-athlete coverage.

## Commit status

The requested commit was attempted as
`test(e2e): isolate mutable Playwright fixtures`, but Git's administrative
worktree is outside the writable sandbox. Git could not create `index.lock` and
returned `Read-only file system`; all changes remain in the working tree.
