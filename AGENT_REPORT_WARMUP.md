# Agent B — Warm-up Plan domain report

## Outcome

Implemented a migration-free, first-class warm-up plan domain/service layer in
`platform-portal/portal/services/warmup_plans.py`.

The service resolves the spreadsheet coaching sequence:

1. general preparation;
2. athlete-specific intervention;
3. lift-specific preparation;
4. barbell/ramp-up preparation;
5. existing session exercise prescriptions remain the work-set boundary.

## Design

- Immutable typed value objects model lift families, phases, instructions,
  reusable protocols, applicability scope, context, resolved plans, overrides,
  and provenance.
- Protocol matching supports explicit athlete IDs/tags, session tags, and
  squat/bench/deadlift families. It makes no injury diagnosis or intervention
  inference.
- Resolution is deterministic by phase, protocol priority/identity, and declared
  step order.
- Coach overrides support removal, replacement, and append. They require actor
  and reason, fail on stale targets, and retain parent provenance on replacement.
- `WarmupProtocolRepository` is the application boundary for the database agent.
  `InMemoryWarmupProtocolRepository` supports reviewed configuration meanwhile.

The later persistence mapping, constraints, version/snapshot expectations, and
integration with `ProgrammingLiftSlot` are documented in
`platform-portal/docs/warmup-plan-domain.md`.

## Files

- `platform-portal/portal/services/warmup_plans.py`
- `platform-portal/tests/test_warmup_plans.py`
- `platform-portal/docs/warmup-plan-domain.md`
- `AGENT_REPORT_WARMUP.md`

No migration or existing migration file was added or modified. No UI, LLM,
Kubernetes, or CI/CD changes were made.

## Verification

- Focused warm-up tests: `11 passed`
- Programming and athlete regression selection: `56 passed`
- Full platform portal suite: `413 passed, 2 skipped`
- `git diff --check`: clean

The shell emitted harmless read-only warnings while loading envman configuration.

## Commit limitation

Commits could not be created because this worktree's Git administrative index is
outside the writable workspace:

`/home/steve/azure-devops-demo/.git/worktrees/v72-warmup-plans-20260809-171331/index.lock`

Git failed with `Read-only file system`. Once that directory is writable, the
intended logical commits are:

```bash
git add platform-portal/portal/services/warmup_plans.py \
  platform-portal/docs/warmup-plan-domain.md
git commit -m "feat(programming): add warm-up plan domain service"

git add platform-portal/tests/test_warmup_plans.py AGENT_REPORT_WARMUP.md
git commit -m "test(programming): cover warm-up plan resolution"
```

The requested `~/AGENT_REPORT_WARMUP.md` is also outside the writable roots, so
this report is stored at the worktree root for handoff.
