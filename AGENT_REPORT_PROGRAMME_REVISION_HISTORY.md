# Agent report: programme revision history

## Outcome

Implemented from base `7d77bdc` in the isolated worktree only. Nothing was merged or deployed.

Programme changes now append immutable revision records containing:

- a per-programme revision number and stable change type;
- a human-readable summary (what changed);
- an explicit supplied reason when present, otherwise an action-specific reason;
- UTC authorship time;
- both the author user reference and a denormalized author label, so attribution survives account changes;
- a versioned, full-fidelity JSON snapshot of the block, ordered weeks, sessions, lift slots, every authored prescription field, warm-up assignments, and warm-up overrides.

The snapshot stores authored values rather than derived UI summaries. Revision history survives deletion of the source block because its block and athlete references use `SET NULL`, while the snapshot and author label remain intact.

## Implementation

- Added `ProgrammeRevision` with application-level update/delete guards.
- Added the central `authored_snapshot()` / `append_revision()` service.
- Covered block create/duplicate/publish/archive; week create/duplicate/extend/delete; session create/insert/duplicate/delete; prescription create/update/delete/reorder; lift-slot save/delete; warm-up create/assign/candidate acceptance/override; generated factory programmes; template-created programmes; and day-template application.
- Added a newest-first coach-facing timeline on the programme block page.
- Added Alembic revision `programme_revision_history`, based on `0015_client_services`. The descriptive identifier and filename deliberately do not consume a numbered migration slot.

## Verification

- Dedicated revision-history regression tests: passing.
- Focused programming, lifecycle, routes, warm-up, template, factory, and migration tests: `96 passed, 1 skipped` across the two focused runs.
- Full portal suite: `528 passed, 2 skipped, 2 failed`. Both failures are pre-existing nutrition-import authorization expectations (`400/404` returned instead of `403`) in `test_v79_authorization_boundaries.py`; they reproduce when that file is run alone and are unrelated to programme history.
- Alembic reports a single head: `programme_revision_history (head)`.
- A clean database upgraded through the full chain to `programme_revision_history` successfully.
- `python -m compileall` and `git diff --check`: passing.
- Ruff and Black were not available in the environment.

## Boundaries

- History is append-only through normal SQLAlchemy model operations; database owners can still mutate rows with direct SQL.
- Revision reasons can be provided as `revision_reason`. Warm-up workflows already require a domain-specific reason; existing editor actions fall back to their precise action summary when no reason is supplied.
- No restore/revert action was added. Historical snapshots are evidence, not a command to overwrite the current authored programme.
