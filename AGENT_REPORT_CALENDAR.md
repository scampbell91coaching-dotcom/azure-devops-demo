# Agent D — Calendar clarity report

## Outcome

Calendar ambiguity is removed from the current UI without a migration or a calendar product. Athlete and coach surfaces now use one schedule projection and explicitly distinguish calendar dates from programme order.

## Findings

- The domain persists block/week/session order but no planned dates. `day_label` is free text.
- Athlete dashboard/programme selected the first unfinished session; coach programming always displayed the first week as current.
- Existing `training_start_date` is athlete-history data, not a block anchor, so deriving dates from it would be unsafe.
- Completed logs are durable athlete history and must not be rewritten when timing changes.

## Changes

- Added `portal/services/training_schedule.py`, a read-only projection for today, next and current progress week.
- Athlete dashboard says “Today & next,” labels undated work “Date not set · programme order,” and explains how shifts are handled.
- Athlete programme shows week/session position and a calendar-status explanation.
- Coach athlete-programming context now uses the same first-unfinished progress week and discloses missing planned dates.
- Added unit coverage for boundary dates, completed, future/today/overdue and missing-date cases, plus 320px E2E assertions.
- Documented authoritative semantics and the Holiday/Travel Mode resolver seam in `platform-portal/docs/v7.4-scheduling-semantics.md`.

## Constraints honored

No migrations, infrastructure changes, merge, or destructive mutation of published programming were performed. Planned-date persistence remains future work; the new projection accepts resolved dates when that layer exists.

## Verification

- `pytest -q tests/test_training_schedule.py tests/test_athlete_dashboard.py tests/test_programming_routes.py` — 14 passed.
- `pytest -q tests/test_programming_core.py tests/test_programming_pack2.py tests/test_coaching_route_security.py tests/test_session_lifecycle.py` — 44 passed.
- `git diff --check` — clean.
- The focused 320px Playwright scenario was attempted, but dependencies are not installed locally and restricted network access prevented `npx` fetching Playwright (`EAI_AGAIN`). The assertion is checked in for the existing E2E environment.
