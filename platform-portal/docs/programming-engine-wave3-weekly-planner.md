# Wave 3 weekly planner

`WeeklyPlanner` is authoritative for new factory proposals. It creates a typed
weekly skeleton containing ordered lift families, primary/secondary placement,
explicit secondary-lower purpose and coach-readable provenance. Wave 2 then
plans exposure intent against that skeleton. Variation, prescription,
assistance and Athlete State adaptation remain outside this boundary.

The coach-confirmed six-day structure is `B / SD / B / B / B / SBD` for five
bench exposures. Six bench exposures retain the same distribution principle
and add bench to Tuesday: `B / SBD / B / B / B / SBD`. Both have exactly two
hard Competition Bench exposures downstream.

For the representative 2x squat, 3x bench, 1x deadlift request, conservative
goldens are:

- 3 days: `BD / SB / SB` (existing historical programme golden)
- 4 days: `B / S / BD / SB`
- 5 days: `B / S / B / D / SB`

These avoid an SBD day because no meet-preparation intent is supplied by the
current factory request. They preserve requested frequency, use squat-before-
bench/deadlift ordering, keep primary bench ahead of deadlift, and spread lower
work where the available days permit.

## Deliberate ambiguity

There is not enough confirmed coaching evidence for a universal 3/4/5-day
split across every possible frequency combination, nor for seven-day training.
The supported planner therefore uses documented stable placement priorities,
rejects schedules that would require invented exposures, caps squat and
deadlift at two, and supports one through six days. `_day_sequence` remains a
read-only compatibility projection with its historical fallback for legacy
rendering; proposal generation does not call that fallback.

The current request has no explicit back-management or coach-authored ordering
field, so deadlift-before-squat is never inferred.
