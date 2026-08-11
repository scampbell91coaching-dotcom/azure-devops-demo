# Block Factory parity agent report — V7.9

## Outcome

Removed the assumption that three accessories is the largest valid generated
session. Automatic selection now fills a deterministic fatigue budget instead
of slicing candidates at a fixed exercise count.

## Policy and compatibility

- Low, Medium and High provide 3, 6 and 9 fatigue units per session.
- Catalogue fatigue defaults remain 3, so existing default-metadata output stays
  at 1, 2 and 3 suggestions respectively.
- Fatigue-1 candidates can produce 3, 6 and 9 suggestions; there is no separate
  count cap. Ranked items that do not fit are skipped deterministically.
- Existing eligibility remains authoritative: active/opt-in status, phase, lift,
  compatibility tags, constraint exclusions and already-used IDs.
- Coach-pinned accessories replace automatic output completely, retain coach
  order and are not limited by the automatic budget.
- Explicit `No assistance` produces zero regardless of volume or grip context.
- Generated reasons now include the fatigue cost and budget. Existing source and
  prescription provenance are unchanged.
- No LLM is used at runtime, and no medical or injury inference was added.
- Signed proposal fields, type, version, integrity calculation and legacy
  defaults are unchanged. Existing proposals therefore retain their established
  compatibility behavior.
- No migration was required.

The complete policy and assumptions are documented in
`docs/v7.6-block-factory-refinement.md`.

## Coverage

Focused tests cover zero assistance, legacy 1-3 output, nine-item automatic
output, seven manual pins replacing automatic output, deterministic repeated
output, metadata compatibility/exclusions, reasons, and provenance.

- Focused AccessoryIntelligence and Block Factory suite: 32 passed.
- Full `platform-portal` suite: 493 passed, 2 skipped.
- Root `make test`: stopped after 19 passed / 1 failed on the pre-existing E2E
  seed expectation omitting the seeder's `Pause Squat`; no changed file is in
  that failure.
- `make lint`: could not start because Ruff is not installed in the workspace.
  `git diff --check` passed.
- Commit attempted with message `feat: remove accessory count ceiling`, but the
  managed worktree's external Git administrative directory is read-only and Git
  could not create its `index.lock`. The complete scoped diff remains ready for
  commit when that directory is writable.
