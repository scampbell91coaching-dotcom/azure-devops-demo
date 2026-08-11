# Calendar / scheduling foundations report

## Outcome

Added a migration-free athlete scheduling projection. It is deliberately scoped
to four existing product concepts: planned programme sessions, meet-day
competition dates, holiday/travel constraints, and weekly check-in timing. It is
not a generic event calendar and does not own or mutate source records.

## Delivered contract

- `portal/services/calendar_scheduling.py` composes the existing training
  schedule and Holiday Mode policies.
- Planned dates remain caller-supplied until the product has explicit persisted
  assignments. Undated sessions never inherit dates from order or `day_label`.
- Competition milestones use meet-day identity, date, name and status. The next
  non-complete competition is derived without changing meet workflow state.
- Holiday/travel decisions overlay dated sessions and preserve the original
  programme. Conflicting periods require coach review rather than arbitrary
  precedence.
- Weekly check-in timing exposes disabled, upcoming, due, overdue and submitted
  states for the current Monday–Sunday window using existing settings semantics.
- Same-day session/competition relationships are explicit so a later UI can warn
  without assuming the session should move.

## Boundaries

No migration number, schema, route, template, infrastructure, merge or deploy
change was introduced. Recurrence, arbitrary appointments, reminders, time-slot
booking and automatic rescheduling are outside this foundation. Persistence can
later adapt existing Meet, check-in, Holiday Mode and planned-session records to
this projection without changing its policy boundaries.

## Verification

- Scheduling plus existing training/holiday/check-in coverage: 32 passed.
- Adjacent meet-day, athlete-dashboard and programming-route coverage: 17 passed.
- Full `platform-portal/tests` suite: 530 passed, 2 skipped, 2 unrelated
  pre-existing failures in nutrition-import authorization boundary assertions
  (expected 403; current routes return 400/404).
- `git diff --check`: clean.
