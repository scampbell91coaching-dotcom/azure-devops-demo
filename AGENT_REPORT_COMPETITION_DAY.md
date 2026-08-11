# Competition-day workflow prototype report

## Outcome

The existing Meet Day workspace now covers the full coach workflow from weigh-in
through post-meet review. Coaches can record official and athlete-specific
bodyweight, plan attempts, record the actual weight and result independently,
schedule warm-ups/attempts, keep warm-up-room and meet notes, advance meet status,
and capture structured review prompts after the competition.

## Delivered

- Reused `Meet`, `MeetEntry`, `MeetLift`, the platform-order board, warm-up
  generator, and calibrated plate-loading service.
- Added competition status, official bodyweight, weight class, weigh-in time,
  meet notes, and post-meet `went well / improve / next actions` controls.
- Added per-athlete weigh-in/bodyweight, warm-up timing/room notes, and meet notes.
- Kept `MeetLift.weight_kg` as the planned load and added independently recorded
  actual load and scheduled time for both warm-ups and attempts.
- Updated the loading sheet and attempt cards to clearly distinguish planned and
  actual values while preserving the existing next-attempt board behaviour.
- Added a versioned, backward-compatible notes envelope for prototype-only state.
  Legacy free-text notes remain readable and editable.
- Added route, rendering, validation, persistence, compatibility, and board tests.

## Migration constraint

No migration file, revision identifier, table, or column was added or changed.
Prototype metadata is stored in the existing notes fields through a small JSON
envelope, while established typed fields continue to hold status, bodyweight,
weight class, planned weight, and outcome. This deliberately avoids consuming a
migration number. A production hardening pass can promote the envelope fields to
typed columns under a separately coordinated schema revision.

## Verification

- Competition-day focused suite: `8 passed`.
- Meet Day, route security, auth, and migration suite: `89 passed, 1 skipped`.
- Full portal suite: `527 passed, 2 skipped, 2 failed`. Both failures are existing
  nutrition-import authorization-boundary expectations (expected 403, received
  400/404); neither failing route nor its tests were touched by this prototype.
- `git diff --check`: passed.
- Python compilation for the changed portal/test files: passed.
- Ruff was unavailable in the existing environment (`No module named ruff`); no
  dependency installation was attempted.

## Explicit exclusions

No migration, merge, deployment, GitOps/Kubernetes change, dependency install, or
external system mutation was performed. The work remains isolated on the supplied
worktree branch based on `7d77bdc` (plus the pre-existing prompt-preservation
commit).
