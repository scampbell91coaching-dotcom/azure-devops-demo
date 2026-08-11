# Competition and bodyweight planning foundation report

## Scope and outcome

Implemented a read-only planning boundary on base `7d77bdc` (the worktree's
preservation commit adds only `AGENT_PROMPT.txt`). The implementation reuses
`Athlete`, `Meet`/`MeetEntry`, `WeeklyCheckin`, and `NutritionCheckIn`. It does
not create a competing athlete/competition model, write planning decisions,
add an Alembic revision, merge, deploy, or touch a cluster.

The service:

- selects the nearest upcoming planned/active structured meet entry, falling
  back to an ISO date in `Athlete.next_competition`;
- returns the chosen competition and bodyweight source references;
- combines dated weekly and nutrition bodyweights, excludes future records,
  and uses `Athlete.bodyweight_kg` only when no dated observation exists;
- keeps `Athlete.weight_class` as context and never guesses a target from it;
- accepts an explicit transient target and calculates signed total and weekly
  change using `Decimal`; and
- returns missing-data/coach-review prompts without changing stored data.

## Files

- `platform-portal/portal/services/competition_bodyweight.py` — immutable
  planning DTOs and the read-only context builder.
- `platform-portal/tests/test_competition_bodyweight.py` — focused provenance,
  precedence, date-boundary, calculation, non-persistence, and validation tests.
- `AGENT_REPORT_COMPETITION_BODYWEIGHT.md` — this handoff.

## Tests

- `pytest -q tests/test_competition_bodyweight.py` — **8 passed**.
- `pytest -q tests/test_competition_bodyweight.py tests/test_meet_day.py tests/test_athlete_state.py tests/test_programming_domain_v7.py` — **26 passed**.
- `git diff --check` — passed.

One initial adjacent-suite command named a non-existent
`tests/test_weekly_programming_intelligence.py`; no tests ran in that invocation.
The relevant programming coverage is in `test_programming_domain_v7.py`, used in
the successful 26-test run above.

## Blockers

No implementation blocker for the read-only foundation. There is deliberately
no route or persistence workflow because the current schema cannot represent a
reviewed bodyweight plan without overloading fields whose meanings differ.

## Schema needs (future coordinated migration)

No migration number was consumed. A future integration should coordinate one
revision for reviewed/persisted planning, likely including:

- a competition-plan record linked to `athletes` and preferably `meets`, with
  explicit target bodyweight, plan status, author/reviewer, timestamps, notes,
  and revision/provenance fields;
- a structured competition link on `training_blocks` so meet date and taper
  context are not inferred from names or free text;
- an explicit distinction between planned weigh-in target and actual weigh-in;
  `Meet.bodyweight_kg` should not silently serve both meanings; and
- canonical federation/division/weight-class identifiers if class-aware rules
  are required. Current free-text `Athlete.weight_class` is display context only.

Any future rate thresholds, weight-cut guidance, or federation-specific limits
need product/coaching review before being encoded; this foundation provides
math and prompts, not medical or nutrition recommendations.

## Integration notes

- Call `build_bodyweight_planning_context(athlete, as_of=..., target_bodyweight_kg=...)`
  inside an application context. The athlete must be persistent because related
  queries use its ID.
- Pass a target only after explicit coach/user input. Omitting it intentionally
  produces no change calculation.
- The nearest upcoming planned/active `MeetEntry` is authoritative over the
  legacy profile string. Completed and past meets are not selected.
- The return objects are frozen dataclasses suitable for a coach preview or for
  enriching programming context. Acceptance/persistence should be a separate,
  audited write action.
- If integrated into weekly programming, add the returned competition source,
  date, target source, and prompts explicitly; do not replace existing coach
  overrides or mutate `Athlete.bodyweight_kg`.
