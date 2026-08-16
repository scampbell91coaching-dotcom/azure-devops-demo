# Programming Intelligence V3 repair handoff

Date: 2026-08-15

## Outcome

- High reported fatigue (8–10) applies an exact, bounded `0.8` volume multiplier while retaining at least one work set per requested exposure.
- Missing fatigue and baseline fatigue (`7`) leave exact S/B/D targets and ranges unchanged.
- Explicit coach-authored weekly S/B/D targets are applied after the fatigue adjustment and win.
- Hook-grip competition context admits hook-specific work when `grip_work_priority=none`; non-hook grip with priority `none` excludes grip-category work.
- Manual `Atlas Stones` specialty programming is preserved through preview and persistence, including coach provenance and exact `5 x 3` prescription metadata.
- Scheduling accepts and exhaustively tests every valid frequency combination across 1–7 training days.
- The exact six-day golden schedule remains `B / SD / B / B / B / SBD`.
- The existing factory disclosure remains: “This remains a reviewable proposal until you accept it.”
- No deployment or push was performed; `main` was not touched.

## Exact test commands and results

No venv exists in this checkout. Tests used the available repository-compatible venv at `/home/steve/azure-devops-demo/platform-portal/.venv`.

Focused final run:

```text
/home/steve/azure-devops-demo/platform-portal/.venv/bin/python -m pytest -q tests/test_block_factory_v3.py
37 passed in 17.52s
```

Relevant Flask/programming suite:

```text
/home/steve/azure-devops-demo/platform-portal/.venv/bin/python -m pytest -q tests/test_accessory_intelligence.py tests/test_programming_pack2.py tests/test_programming_references.py tests/test_block_factory_v2.py tests/test_programming_routes.py tests/test_programming_templates.py tests/test_volume_progression.py tests/test_accessory_athlete_state.py tests/test_programming_copilot_intent.py tests/test_programming_json_security.py tests/test_programming_athlete_state.py tests/test_programming_domain_v7.py tests/test_programming_core.py tests/test_block_factory_v3.py tests/test_programming_engine_foundation.py tests/test_proposal_explanations.py
127 passed in 27.36s
```

The exhaustive 1–7 scheduling matrix is exercised by `test_frequency_scheduler_exhaustively_covers_every_valid_1_to_7_day_request` in the passing focused and broader runs. The golden schedule is exercised by `test_six_day_golden_schedule_is_preserved_exactly`.

`git diff --check` passed with no output.

## Commit status

Base SHA: `b4b84db`

Repair commit SHA: unavailable in this execution environment. The checkout's `.git` directory is mounted read-only, and `git commit` fails before creating a commit:

```text
fatal: Unable to create '.git/index.lock': Read-only file system
```

All intended source, template, test, and handoff changes remain in the working tree pending a writable Git metadata mount. This is the only incomplete required handoff step.
