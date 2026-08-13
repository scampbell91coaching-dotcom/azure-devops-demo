# Paid-beta SLOs and skipped Python test audit

This is the Powerlifting portal's paid-beta operating contract. It defines
objectives and proposed alerts; it does not claim that production telemetry or
alert delivery is active. Production activation requires the validation gate in
[production-observability.md](production-observability.md).

## Python skip audit

The audit command was run locally from `platform-portal`:

```bash
python -m pytest -q -rs
```

It reported `766 passed, 2 skipped` and identified exactly these tests:

| Test | Observed skip reason | Classification | Paid-beta disposition |
|---|---|---|---|
| `tests/test_database_migrations.py::test_upgrade_on_empty_postgresql_when_available` | `POSTGRES_TEST_DATABASE_URL is not configured` | Environment-only test gap: the test needs an empty, disposable PostgreSQL database. It proves all migrations apply from empty, `verify-schema` succeeds, the complete table inventory is present, and the sole head is `0023_organisation_invitation_delivery`. | Not an application defect, but fresh passing PostgreSQL evidence is a release gate before paid beta. SQLite coverage is not an adequate substitute. |
| `tests/test_sqlite_postgres_migration.py::test_full_migration_dry_run_refusal_replace_rollback_and_sequence` | `POSTGRES_TEST_DATABASE_URL or psycopg is not configured`; in this audit `psycopg 3.2.10` was installed, so the absent URL caused the skip. | Environment-only test gap: the integration test creates an isolated schema and needs PostgreSQL plus the `psycopg` driver. It exercises the SQLite-to-PostgreSQL migration, refusal/replace behavior, rollback and sequence handling. | Not an application defect, but passing evidence is required before any legacy SQLite data import or paid-beta release that relies on that path. If no legacy import is in beta scope, record it as not applicable to the launch path, while still running the clean PostgreSQL upgrade test above. |

Neither skip authorizes a fail-open fallback, a shared database, or a production
database test. The conditional skip is useful for ordinary SQLite-only local
runs; the release proof must explicitly supply its dependencies and fail if the
tests skip.

### How to unskip and prove both tests

1. Provision a disposable local/CI PostgreSQL instance. Use a dedicated empty
   database owned by the test identity; never use production or a persistent
   developer database. Install the portal requirements so `psycopg` is present.
2. Set `POSTGRES_TEST_DATABASE_URL` to that database using an approved secret
   injection mechanism. Do not print or persist the URL in logs or evidence.
3. Run the two node IDs and write machine-readable results:

   ```bash
   python -m pytest -q -rs --junitxml=/tmp/powerlifting-postgres-proof.xml \
     tests/test_database_migrations.py::test_upgrade_on_empty_postgresql_when_available \
     tests/test_sqlite_postgres_migration.py::test_full_migration_dry_run_refusal_replace_rollback_and_sequence
   ```

4. Require exit zero, `2 passed`, and JUnit totals of two tests with zero skipped,
   errors or failures. This explicit check matters because pytest exits zero when
   tests skip. Also retain the asserted sole head
   `0023_organisation_invitation_delivery`. Save the sanitized command, commit,
   Python/PostgreSQL versions and test summary as release evidence.
5. Destroy the disposable database. In CI, make the JUnit total check fail the
   job on an unexpected skip.

The empty-database test itself rejects a reused database. The import test creates
and drops a process-specific schema, but its containing database must still be
disposable and isolated from concurrent jobs.

## Paid-beta service-level objectives

Initial window: rolling 28 days, reviewed weekly. The scope is the public
Powerlifting portal and authenticated coach/athlete journeys. Planned maintenance
counts as downtime unless communicated before the window. Health probes alone do
not satisfy the availability SLI; use external requests and exclude only clearly
identified synthetic traffic from request-rate SLIs.

| Signal | SLI and paid-beta objective | Proposed alert and response |
|---|---|---|
| Availability | Successful external HTTPS transactions divided by valid attempts, where success is the expected HTTP result and completes within 5 seconds. **99.5% over 28 days** (about 3h 22m error budget). Measure from at least two locations every 2 minutes and include a minimal authenticated journey when safely available. | **Page:** both locations fail or checks are missing for 5m. **Ticket:** 28-day availability below 99.7%, giving warning before budget exhaustion. |
| HTTP error rate | Non-synthetic portal requests returning 5xx divided by all non-synthetic requests. **At least 99.5% 5xx-free over 28 days.** Report 4xx separately; do not count expected auth/validation 4xx as server failure. | **Page:** 5xx >5% for 10m with at least 20 requests. **Warn:** >1% for 15m with at least 50 requests. Add multi-window burn alerts once the SLI is validated: 14.4x burn over 1h paired with 6x over 6h (page), and 3x over 6h paired with 1x over 3d (ticket). |
| p95 latency | p95 server/request duration for valid non-synthetic requests, split by route template and excluding health/metrics. **p95 <=1.0s over rolling 28 days**, with no critical authenticated route hidden by aggregation. | **Warn:** p95 >1s for 15m with at least 20 requests. **Page:** p95 >2s for 10m with at least 20 requests, or availability begins failing. |
| DB connection pressure | Maximum active plus waiting application connections divided by the lower of the configured pool capacity and safe PostgreSQL connection budget. **Below 70% for 99% of five-minute samples; no pool-acquisition timeout.** | **Warn:** >70% for 10m. **Page:** >85% for 5m, any sustained waiter/pool timeout for 2m, or connection refusal affecting requests. Activation requires a real pool/server metric; SQL error telemetry alone is insufficient. |
| Migration failure | Every release migration Job completes once, exits zero, passes `verify-schema`, and reports exactly the canonical head before new code receives traffic. **100% per release; zero error budget.** | **Page immediately:** Job failed, deadline exceeded, missing at the release checkpoint, schema verification failed, or head differs from `0023_organisation_invitation_delivery`. Stop the release; preserve sanitized evidence and forward-fix. Never blindly retry or downgrade. |
| Collector freshness | The five-minute `platform-status-collector` snapshot has valid `generated_at` and age **<=15m for 99.5% of five-minute samples**. Malformed, future-dated and unavailable snapshots are failures. | **Warn:** age >10m. **Page:** age >15m or two consecutive failed/missed Jobs. This is a dead-man signal and must use an independent evaluator, not the collector being watched. |
| Release evidence freshness | For each release decision, evidence is readable, schema-valid, `ready`, matches the candidate commit, contains no skipped mandatory check, and is **<=24h old** (matching the fail-closed reader). **100% per release; zero error budget.** | **Block/page at release time:** absent, malformed, stale, wrong commit, `not_ready`, or mandatory check skipped/failed. Release evidence is event-scoped, not a continuously regenerated operational SLI. |
| Background jobs | No general asynchronous worker/queue is implemented in the audited portal. The applicable recurring background work is the platform-status CronJob; migration is release-scoped and covered above. **99% successful scheduled collector runs over 28 days; no run exceeds its 120s deadline.** | **Warn:** one failed run or duration >90s. **Page:** two consecutive failed/missed runs, duration/deadline >120s, or resulting snapshot >15m old. Define job-specific SLOs before adding any invite/notification worker; do not claim generic worker coverage now. |

## Measurement and activation rules

- Use low-cardinality route templates, status classes and fixed operation labels;
  never put organisations, athlete IDs, email addresses, query strings or raw
  paths in telemetry.
- Dashboard numerator, denominator, exclusions, minimum-traffic gates and time
  zone must be visible. Missing telemetry is unknown/failing evidence, never a
  healthy zero.
- Page alerts require a named on-call owner, versioned runbook, grouping and
  inhibition. Ticket alerts need a named working-hours owner. Exercise both via a
  non-production receiver before beta and record delivery and resolution.
- Review thresholds after two weeks of representative beta traffic, but do not
  retroactively redefine an SLI to erase an incident. Record SLO changes with an
  effective date.
- Current portal metrics, database-pressure metrics, public availability tests
  and alert routing are not proven active. Until staged end-to-end validation is
  recorded, these are beta entry criteria rather than achieved SLOs.
