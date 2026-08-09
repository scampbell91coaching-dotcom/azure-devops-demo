# Agent A report — Accessory Intelligence V7.2

## Outcome

Implemented a reusable, deterministic accessory-intelligence foundation on the
existing canonical `exercises` table. Block Factory can now select up to one
compatible, coach-enabled accessory per session without a manually enumerated
block pool. Manual pins fully replace suggestions, and the coach can explicitly
select no assistance.

## Data model and migration

Inspected the Alembic graph before adding the only migration in this batch. The
previous head was `0012_athlete_accounts`; the new single head is
`0013_accessory_intelligence`.

The existing Exercise model already covers canonical identity/name, movement,
category, muscle emphasis, equipment, fatigue, defaults, progressions,
regressions, constraints, and active state. V7.2 adds only selection-specific
fields: `auto_select`, `lift_relevance`, `training_phases`,
`compatibility_tags`, and `coach_priority`. Existing rows default to opted out.

## Selection behavior

- Repository boundary queries active, accessory-suitable, explicitly enabled rows.
- Service filters exact phase, lift relevance, compatibility, and excluded
  constraint tags.
- Stable ordering is coach priority descending, fatigue ascending, then name.
- Reasons shown in preview include coach opt-in, matched lift/phase, priority,
  and fatigue cost.
- At most one unused suggestion is added per day.
- Coach-pinned accessories override all automatic suggestions.
- “No assistance” remains explicit.
- Suggested accessories use catalogue default sets/reps when configured.
- No LLM, athlete diagnosis, or athlete-state changes were introduced.

## Tests

- Full portal suite: `406 passed, 2 skipped`.
- Expanded focused suite: `51 passed, 1 skipped`.
- Migration tests cover schema presence and preservation of legacy opt-out.
- Alembic reports one head: `0013_accessory_intelligence`.
- `git diff --check` passes.

## Documentation

Selection and model details are in
`platform-portal/docs/accessory-intelligence.md`.

## Environment limitations

The requested `~/AGENT_REPORT_ACCESSORY.md` could not be written because the
home directory is read-only; this workspace-root copy contains the report.
Logical commits could not be created because this worktree's Git index is under
`/home/steve/azure-devops-demo/.git/worktrees/...`, also read-only. The attempted
commit made no index or repository changes. All implementation changes remain
in the working tree for the owning process to commit.
