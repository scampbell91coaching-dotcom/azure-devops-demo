# Agent C — Coach review queue

## Outcome

Completed athlete training sessions now appear in the coach dashboard's single
action queue. The queue is derived entirely from existing
`training_session_logs` and `training_set_results` records; no migration or new
schema was introduced.

Each training item shows:

- athlete name with a link to the athlete dashboard;
- session name;
- exact completion date and time;
- up to two athlete set notes, or a completed/skipped set summary when there are
  no notes;
- the derived `Needs review` state;
- a direct `Review session` link to actual-versus-prescribed results and notes.

The unified queue is sorted deterministically by oldest submission/completion
first, then kind and persisted ID. Completed logs with no valid completion
timestamp and in-progress logs are excluded.

## Authorization and isolation

The queue is rendered only on the authenticated coach surface. Its links use the
existing coach training-detail route, which verifies that the log belongs to the
athlete in the URL and returns `404` for mismatches. Athlete accounts remain
blocked from that route with `403`. Existing authorization coverage for those
cases remains passing.

The application currently has a single coach role with no coach-to-athlete
assignment model, so there is no narrower coach tenancy boundary to derive or
enforce in this iteration.

## Review-state decision

Training logs have no persisted coach acknowledgement. Consequently every
completed training log is truthfully labelled `Needs review`; the change does
not imply that opening a detail page records a durable review. A future
reviewed/unreviewed workflow would require explicit persisted acknowledgement
and was intentionally not smuggled into this schema-free beta change.

## Tests

- Service coverage verifies completed versus in-progress filtering, multiple
  athletes, oldest-first ordering, note/fallback summaries, derived review
  state, and stable results across a second service build (reload semantics).
- Existing authorization tests verify athlete isolation and mismatched
  athlete/log IDs.
- The browser journey now covers: athlete completes a session with a note →
  coach signs in → coach sees the session and note summary on `/coach` → coach
  follows `Review session` to the persisted detail.

Verification performed:

```text
pytest -q tests/test_coach_dashboard.py tests/test_athlete_training_log.py
20 passed

pytest -q
456 passed, 2 skipped
```

The targeted Playwright command was attempted with the repository's required
disposable-test guard, but could not run because Playwright was not installed
locally and restricted network access prevented `npx` reaching npm
(`getaddrinfo EAI_AGAIN registry.npmjs.org`). No shared or external environment
was used.

## Files changed

- `platform-portal/portal/services/coach_dashboard.py`
- `platform-portal/templates/coach/dashboard.html`
- `platform-portal/tests/test_coach_dashboard.py`
- `e2e/tests/athlete-training.spec.ts`
- `AGENT_REPORT_COACH_REVIEW.md`

No infrastructure was changed and no merge was performed.
