# Powerlifting beta load package

This package models the Traditional Strength powerlifting workload. It is for a
local or disposable, seeded environment only. The script refuses non-loopback
targets unless `PL_ALLOW_REMOTE=true`; that override is for an explicitly
approved non-production test environment, never production.

## Run

Install [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) outside the
repository, start a disposable portal, and provide seeded identities/records:

```sh
k6 run \
  -e BASE_URL=http://127.0.0.1:5000 \
  -e COACH_COOKIE='session=<coach-session-cookie>' \
  -e ATHLETE_COOKIE='session=<athlete-session-cookie>' \
  -e ATHLETE_ID=1 -e SESSION_ID=1 -e BLOCK_ID=1 \
  performance/k6/pl_beta.js
```

Use a session cookie created in that environment. The test does not automate
login because login rate limiting is not the workload under test and passwords
must not be stored in scripts. IDs must belong to the supplied identities.
CSRF-protected POSTs need `CSRF_TOKEN` from the athlete session.

Available profiles are `smoke` (default), `beta`, and `peak`; select one with
`-e PROFILE=beta`. Writes are disabled by default. To test logging against
throwaway seed data, add `-e ENABLE_WRITES=true -e CSRF_TOKEN=...`. The write
scenario saves progress only; it does not complete sessions or submit weekly
check-ins, avoiding unbounded record creation. Set `MEAL_PLAN_PDF_PATH` only
when a real PDF access route exists; until then the athlete meal-plan HTML route
is the measured delivery surface.

Results include tags for every workload. Override thresholds only to test a
documented experiment; the committed values are the beta release gates.

## Profiles and traffic mix

The beta assumption is 8--15 coaches and 150--300 athletes, with traffic
clustered around morning coach review and after-work training. Virtual users
represent active concurrent browser journeys, not registered accounts.

| Profile | Concurrent activity | Duration | Purpose |
| --- | ---: | ---: | --- |
| smoke | 1 coach + 1 athlete | 30 s | route/auth/fixture check |
| beta | 6 coach + 24 athlete + 2 factory | 8 min | expected beta busy period |
| peak | 12 coach + 48 athlete + 4 factory | 5 min | short 2x beta headroom |

Athlete iterations weight programme/session reads and performance data most
heavily, with check-ins, nutrition, and meal-plan access less often. Coach
iterations cover `/coach`, athlete detail, check-in queue, nutrition dashboard,
and the performance chart API. Block previews are isolated because they are
CPU-heavy POSTs and create proposal records in the current implementation.

## Release thresholds

These are server-response gates, not browser Core Web Vitals:

| Class | p95 | p99 | Error rate |
| --- | ---: | ---: | ---: |
| HTML reads | 750 ms | 1.5 s | < 1% |
| performance JSON | 500 ms | 1.0 s | < 0.5% |
| session progress save | 750 ms | 1.5 s | < 1% |
| block factory preview | 2.0 s | 4.0 s | < 1% |
| meal-plan/PDF access | 1.0 s | 2.0 s | < 1% |

During the beta profile, application CPU should remain below 70% sustained
(85% short peak), memory below 75% of its limit with no monotonic post-test
growth, database pool use below 70% sustained, and database CPU below 60%.
There should be no OOM/restarts, pool timeouts, or lock/deadlock errors. Compare
request rate, query latency, connection use, CPU, memory and GC from five
minutes before the run until ten minutes after it. A pass requires all request
gates and resource gates; k6 alone cannot certify resource gates.

## Query-growth audit

Highest-risk code paths found during review:

* Coach dashboard loads complete athlete, check-in, nutrition, completed-log,
  settings, and block tables. Query count is constant, but rows and Python-side
  sorting grow with total tenant history; retention/windowing is the key risk.
* Athlete detail loads every nutrition check-in then sorts and annotates them in
  Python. Response work grows with lifetime history.
* Coach performance aggregation eager-loads logs/results but filters a selected
  block in Python, traversing `log.session.week.block`; keep its query-count
  audit and watch row volume.
* Performance charts use a bounded date range and one joined training query,
  but response size and calculation are linear in set results; bodyweight has a
  200-row cap. The regression test pins constant SELECT count as history grows.
* Nutrition dashboard uses three bulk reads (athletes, nutrition check-ins,
  weekly check-ins), then groups/sorts all history in Python. The regression
  test protects against N+1, while load telemetry must catch row-growth cost.
* Meal-plan list methods deserialize each JSON snapshot in Python. They avoid
  relationship N+1s, but large plan histories and large embedded day/item
  payloads can increase CPU and allocation pressure.
* Block factory preview calculates weeks/sessions/accessories in process and
  persists proposal state. It needs separate saturation monitoring and should
  never be aimed at production.

Meal-plan PDF export is an entitlement but no PDF delivery route or file-store
implementation exists in this snapshot. Do not fabricate a URL or benchmark
HTML as if it were PDF. When implemented, set `MEAL_PLAN_PDF_PATH` and retain
the access-control tests alongside the latency gate.

