# Traditional Strength platform performance audit

**Audit date:** 3 August 2026  
**Scope:** repository-grounded static review; no production traces, query plans, load tests, or invented benchmark results  
**Change scope:** documentation only

## Executive summary

The main scaling risk is unbounded data retrieval followed by Python-side aggregation and template traversal. The coach and nutrition dashboards read whole tables or whole histories, check-in and exercise-library lists have no pagination, and several programming pages produce confirmed N+1 query patterns through lazy SQLAlchemy relationships. The current schema mostly has single-column foreign-key indexes; it lacks the composite indexes that match the application's common `WHERE ... ORDER BY ... LIMIT 1` access paths.

The platform also has useful foundations: primary-key lookups use `Session.get`, the athlete dashboard deliberately eager-loads its block hierarchy, the nutrition dashboard bulk-loads rather than querying once per athlete, migrations are separated from normal production startup, the Helm deployment has startup/readiness/liveness probes and graceful termination, and production resource requests and limits are explicit.

Findings below describe code shape, not measured latency. Index proposals must be validated with representative PostgreSQL data and `EXPLAIN (ANALYZE, BUFFERS)` before implementation.

## 1. Existing performance strengths

- The athlete dashboard scopes every history query to one athlete and takes only the latest row with `.first()`. It uses `selectinload` for block → weeks → sessions, preventing N+1 queries for the hierarchy it renders (`portal/services/athlete_dashboard.py:33-64`).
- The nutrition dashboard performs three bulk reads and uses `joinedload` for both check-in-to-athlete relationships rather than querying per athlete (`portal/services/nutrition_dashboard.py:70-87`).
- Detail routes generally use identity/primary-key retrieval through `db.session.get`, including programming blocks, weeks and sessions (`portal/programming_routes/blocks.py:57-61`, `weeks.py:28-36`, `sessions.py:55-68`).
- Foreign keys used for parent-child lookup have indexes: `weekly_checkins.athlete_id`, `nutrition_checkins.athlete_id`, `training_blocks.athlete_id`, `training_weeks.block_id`, `training_sessions.week_id`, and `exercise_prescriptions.session_id` (`migrations/versions/0001_baseline_coaching_schema.py:233-240,255-256,287,301,314,344-348`).
- Exact exercise names and template codes are uniquely indexed, supporting seed lookups and duplicate prevention (`migrations/versions/0001_baseline_coaching_schema.py:107-110,121`).
- Normal production startup does not call `create_all`, mutate columns, or seed: legacy initialization defaults to `app.testing`, while the production Helm release runs `flask db upgrade` in a pre-upgrade Job (`portal/__init__.py:47-84`; `flask-app/values-production.yaml:18-30`; `flask-app/templates/migration-job.yaml:1-16`).
- Gunicorn already has multiple processes and threads (two workers, four threads), bounded request timeouts, and a cheap application-only `/health` endpoint (`Dockerfile:28-31`; `portal/api/health.py:1-8`).
- AKS configuration includes CPU/memory requests and limits, zero-unavailable rolling updates, startup/readiness/liveness probes, pre-stop delay, and a termination grace period (`flask-app/values-production.yaml:51-80`; `flask-app/templates/deployment.yaml:13-18,79-110`).
- Browser tests are deterministic, isolate seeded data, disable full parallelism, use one CI worker, and retain traces only on failure (`playwright.config.ts:6-30`; `e2e/support/seed_database.py:19-83`). This favors stability and diagnosis, although it is not performance measurement.

## 2. Confirmed N+1 risks

These are confirmed from default lazy relationships and actual template/service access. Query counts should still be captured in tests to establish exact counts.

| Path | Confirmed query pattern | Evidence | Recommendation |
|---|---|---|---|
| `/check-ins` | One query loads every check-in, then rendering `item.athlete` can issue one lazy query per distinct athlete. | `portal/checkins.py:42-45`; `templates/checkins/index.html:8-13`; relationship defaults to lazy select at `portal/models/checkins.py:98-105`. | Add `joinedload(WeeklyCheckin.athlete)` and paginate. |
| `/programming` | One query loads blocks; `block.weeks|length` causes one lazy collection query per block. `block.athlete` is also lazy, although loading all athletes immediately beforehand may satisfy many-to-one lookups from the session identity map. | `portal/programming_routes/athletes.py:33-38`; `templates/programming/index.html:19`; relationships at `portal/models/programming.py:42-48`. | Remove the unused full-athlete load if possible; fetch week counts with aggregation or eager-load a bounded page of blocks. |
| Block detail | Rendering each block's weeks loads one collection; then `week.sessions|length` issues one query per week. | `portal/programming_routes/blocks.py:57-62`; `templates/programming/block.html:5`; `portal/models/programming.py:66-71`. | `selectinload(TrainingBlock.weeks).selectinload(TrainingWeek.sessions)` for a bounded block, or aggregate session counts. |
| Week editor | Loading `week.sessions` issues one query and iterating each `session.prescriptions` issues one query per session. Accessing `week.block` and then `block.athlete` adds lazy many-to-one queries. | `portal/programming_routes/weeks.py:28-37`; `templates/programming/week.html:29-48`; `portal/models/programming.py:65-95`. | Eager-load block/athlete, sessions and prescriptions in the route. |
| Block/week duplication | `source.weeks`, each `source_week.sessions`, and each `source_session.prescriptions` are traversed lazily, creating hierarchy-shaped N+1 reads before writes. | `portal/programming_services/blocks.py:21-52`; `portal/programming_services/prescriptions.py:103-105`. | Load the full source graph with `selectinload` before copying; measure flush/write amplification separately. |
| Week copy/extend | Each source session's prescriptions is lazy-loaded; repeated `extend` copies the just-created graph and performs repeated flushes. | `portal/programming_services/weeks.py:58-78,97-112`. | Preload the source graph and construct objects before fewer flush boundaries. Preserve transactional validation. |

The coach dashboard's use of `item.athlete` is **not classified as a confirmed N+1** because it first loads every athlete into the same SQLAlchemy session (`portal/services/coach_dashboard.py:63,77,208-237`); the identity map can satisfy those many-to-one references. It remains wasteful because all rows are loaded.

## 3. Expensive queries and processing

### High confidence

- `CoachDashboardService.build` reads all athletes, weekly check-ins, nutrition check-ins, settings and training blocks, then filters, groups, sorts, and finds latest records in Python (`portal/services/coach_dashboard.py:61-75,77-149,152-255`). Cost and response memory grow with lifetime history, not current dashboard size. Move cutoffs, statuses, latest-per-athlete selection and review predicates into SQL. PostgreSQL window functions, `DISTINCT ON`, filtered aggregates, or lateral joins are candidates to compare with plans.
- The nutrition dashboard loads all athletes and all matching nutrition-bearing history, groups and sorts records in Python, and retains full per-athlete histories merely to derive latest and recent values (`portal/services/nutrition_dashboard.py:70-135`). Select only relevant columns and bounded/latest rows per athlete in SQL.
- Exercise search applies a leading-and-trailing wildcard `ILIKE '%term%'` across six columns and returns all matches (`portal/exercise_library.py:24-50`). Ordinary B-tree indexes cannot accelerate these contains predicates effectively.
- The global check-in index orders and materializes the whole table (`portal/checkins.py:42-45`), while athlete history materializes the athlete's complete history (`portal/services/checkins.py:38-43`).
- The programming index loads all athletes and all blocks, even though the template only displays blocks; it then counts lazy weeks per block (`portal/programming_routes/athletes.py:33-38`; `templates/programming/index.html:19`).
- Programme creation/copy paths call `flush()` for each new block/week/session (`portal/programming_templates.py:153-180`; `portal/programming_services/blocks.py:21-52`; `portal/programming_services/weeks.py:58-78`). This guarantees identifiers but increases database round trips for large generated programmes.

### Moderate confidence; verify with plans

- Latest athlete dashboard queries combine athlete filters with descending timestamp/id ordering (`portal/services/athlete_dashboard.py:39-64,120-151`). With only single-column foreign-key indexes, PostgreSQL may sort the athlete's history.
- Coach-response lookup filters non-empty text and orders by review/submission time (`portal/services/athlete_dashboard.py:117-151`). A partial index may help if responded rows are sparse.
- Pending and duplicate check-in checks use athlete plus a week/date range or exact date (`portal/services/checkins.py:58-63,119-127`; `portal/models/checkins.py:38-54`). They need a composite access path, not only `athlete_id`.

## 4. Missing or questionable PostgreSQL indexes

The migration defines mostly individual indexes (`migrations/versions/0001_baseline_coaching_schema.py:107-110,233-240,255-256,287,301,314,344-348`). Validate the following against production-like cardinality and write cost:

| Priority | Candidate | Supports | Notes |
|---|---|---|---|
| P0 | Unique `(athlete_id, week_ending)` on `weekly_checkins` | Duplicate validation and due checks | The application checks uniqueness in code (`portal/services/checkins.py:119-127`) but the schema does not enforce it. This is both correctness and performance work; first detect/resolve duplicates. |
| P0 | `(athlete_id, submitted_at DESC, id DESC)` on `weekly_checkins` | Latest check-in and athlete history | Matches `portal/services/athlete_dashboard.py:52-55`; consider `week_ending DESC, submitted_at DESC` instead/additionally for history (`portal/services/checkins.py:38-43`). Choose using observed calls and plans. |
| P0 | `(athlete_id, submitted_at DESC, id DESC)` on `nutrition_checkins` | Latest nutrition per athlete | Existing separate indexes on athlete and submitted time do not match both filter and order (`portal/services/athlete_dashboard.py:60-64`). |
| P1 | `(athlete_id, status, created_at DESC, id DESC)` or a partial active index on `training_blocks` | Current block lookup | Match `portal/services/athlete_dashboard.py:39-48`; compare a partial `WHERE status = 'active'` index if active rows are selective. |
| P1 | `(block_id, position)`, `(week_id, position)`, `(session_id, position)` | Ordered relationship loads | Current indexes cover only foreign keys; relationships always order by position (`portal/models/programming.py:43-48,66-71,90-95`). |
| P1 | Partial review queues | Weekly `status='submitted'`; nutrition `reviewed=false` ordered by submission | Boolean/status-only indexes are often low-selectivity. Partial indexes with ordering may outperform `ix_nutrition_checkins_reviewed`; verify queue size and write cost. |
| P2 | `(last_name, first_name, id)` on `athletes` | Repeated coach lists | Current schema indexes status/email/created time, not name sorting (`portal/models/athlete.py:12-29`). Likely useful only once athlete count is material. |
| P2 | `pg_trgm` GIN indexes for chosen exercise search expression(s) | Contains search | Requires extension and migration. Six separate trigram indexes may be excessive; benchmark a generated/search-document expression or PostgreSQL full-text search instead. |

Questionable existing indexes include single-column booleans such as `nutrition_checkins.reviewed` and `exercises.active`; their selectivity may be poor. Do not remove them without `pg_stat_user_indexes`, table cardinality, and query-plan evidence. PostgreSQL does not automatically index foreign keys, so the existing FK indexes are appropriate.

## 5. Pagination gaps

No application route calls SQLAlchemy pagination, `LIMIT` for user-facing lists, or cursor handling. The only repository `.limit()` is for platform snapshot history (`portal/repositories/platform_snapshot_repository.py:20-25`). Gaps include:

- global check-ins (`portal/checkins.py:42-45`);
- athlete check-in history (`portal/services/checkins.py:38-43`);
- exercise library and search results (`portal/exercise_library.py:24-50`);
- athletes list (`portal/athletes.py:72-74`);
- athlete nutrition history (`portal/athletes.py:122`);
- programming index and per-athlete block history (`portal/programming_routes/athletes.py:9-38`);
- coach dashboard review/recent/nutrition sections, which are created from complete tables (`portal/services/coach_dashboard.py:61-149`);
- nutrition dashboard history used to calculate cards (`portal/services/nutrition_dashboard.py:70-135`).

Prefer keyset pagination for append-mostly histories, using stable keys such as `(submitted_at, id)`. For small administrative lists, page-number pagination is acceptable if the `COUNT(*)` cost is measured. Always include `id` as a deterministic tie-breaker; several current orderings omit it (`portal/checkins.py:44`; `portal/services/checkins.py:41-42`).

## 6. Search and filtering concerns

- Exercise search sends every keystroke only when the form is submitted, which avoids client-generated request storms, but the server query is a six-column contains scan (`portal/exercise_library.py:24-50`; `templates/exercises/index.html`).
- Search input has no repository-visible maximum length or normalized token strategy. Add an application limit, minimum useful term length, escaped semantics where appropriate, and pagination before enabling richer/live search.
- Movement equality can use `ix_exercises_movement`, but combining movement with contains search and ordering by movement/name needs plan validation. If movement is specified, ordering by movement is redundant.
- Exercise name creation checks with exact case-sensitive equality before relying on a unique index (`portal/exercise_library.py:60-75`). PostgreSQL's ordinary unique text index permits case variants; use `citext` or a unique index on normalized name only if product semantics require case-insensitive uniqueness.
- Dashboard filtering is largely Python-side. Push date/status/review predicates into SQL so PostgreSQL can discard rows before transfer (`portal/services/coach_dashboard.py:77-149`).

## 7. Template and rendering concerns

- Lazy relationship traversal in programming and check-in templates causes the confirmed N+1 patterns above (`templates/programming/index.html:19`; `block.html:5`; `week.html:29-48`; `checkins/index.html:8-13`). Routes should supply fully shaped view data; templates should not trigger database access.
- Templates render unbounded collections as complete HTML documents. Pagination reduces database time, Python object count, Jinja work, response bytes, and browser layout together.
- The operations base template loads five page-specific stylesheets plus the athletes stylesheet on every page, regardless of need (`templates/base.html:7-15`). Split common CSS from page-specific blocks or produce a measured bundle; HTTP/2 reduces connection cost but not unused CSS parse/style cost.
- Programming templates contain dense one-line markup (`templates/programming/index.html:19`; `templates/programming/block.html:3-5`). This is maintainability rather than a material runtime problem, but it makes accidental relationship access difficult to review.
- `day_templates()` deep-copies a static dictionary on each session-editor request (`portal/programming_templates.py:71-72`; `portal/programming_routes/sessions.py:55-68`). The structure is tiny, so this is low priority.

## 8. Static-asset concerns

- `static/img/traditional-strength-logo.png` is 650,839 bytes in the repository and is rendered twice on public guide pages (`templates/public/base.html:27-34,60-66`). Create appropriately dimensioned WebP/AVIF variants, retain a fallback if required, and set intrinsic `width`/`height` to reduce transfer and layout shift. Measure visual quality before replacing it.
- Static URLs mostly lack content hashes or consistent versioning; only selected stylesheets use query strings (`templates/base.html:12-15`; `templates/public/base.html:18-21`). Establish immutable fingerprinted assets and long cache lifetime at the ingress/CDN; keep HTML short-lived.
- The Flask image serves static files from the same Gunicorn service (`portal/__init__.py:28-33`; `Dockerfile:31`). Production should offload static delivery to an ingress/CDN/object store or at least verify ingress caching and compression. The repository shows no portal-specific CDN or compression configuration.
- Chart.js is loaded from jsDelivr on the history page without `defer`, integrity metadata, or a repository-controlled fallback (`templates/history.html:95-96`). It can block parsing and introduces third-party latency. Pin/self-host or add SRI and `defer` after functional testing.
- Coach/public scripts correctly use `defer` (`templates/coach/base.html:114-117`; `templates/public/base.html:82-90`), an existing strength.
- Do not automatically bundle every file: page-specific payloads are currently small. Use coverage and request waterfalls to choose between fewer requests and unused bytes.

## 9. Startup, migration, and seed concerns

- Production startup is appropriately schema-neutral because `LEGACY_STARTUP_INITIALIZATION` defaults false outside tests (`portal/__init__.py:42-49,75-84`). Keep it explicitly false in production configuration to prevent an accidental test-like configuration from performing DDL and seed queries in every Gunicorn worker.
- Legacy/test startup calls `create_all`, introspection/alter helpers, and the seed routine (`portal/__init__.py:75-84`). Gunicorn imports `app:app` in each worker, so enabling that flag would duplicate startup work and create races.
- The seed routine performs three exercise lookups, six template lookups, lazy-loads each template's exercises, and flushes new rows individually (`portal/seed_programming_engine.py:57-98`). It is idempotent for the built-in rows but should remain an explicit release/admin operation, not a readiness dependency. Batch-fetch existing names/codes if the catalogue expands.
- The E2E server uses `create_all` and deterministic inserts (`e2e/support/seed_database.py:19-83`). This is suitable for isolated ephemeral SQLite, but it does not exercise Alembic migration duration, PostgreSQL plans, network latency, connection limits, or production-scale seeds.
- The migration Job has no retry (`backoffLimit: 0`) and a ten-minute deadline (`flask-app/values-production.yaml:23-30`). Zero retry can be desirable for safe human investigation; record migration duration and lock waits before changing it. Use PostgreSQL `lock_timeout` and `statement_timeout` deliberately for migrations rather than relying only on the Kubernetes deadline.
- The migration Job reuses web-container resource settings (`flask-app/templates/migration-job.yaml:50-51`). Large index builds or data migrations have a different resource profile; define measured migration-specific resources.
- Alembic `0002` uses batch table alteration (`migrations/versions/0002_add_exercise_knowledge_columns.py:16-52`). Confirm generated PostgreSQL DDL and locking for future revisions; plan concurrent index creation separately where deployment tooling permits it.

## 10. PostgreSQL tuning priorities

1. Enable and review `pg_stat_statements`; rank queries by total time, mean/p95 application duration, calls, rows and shared-buffer reads. Reset only in a controlled measurement window.
2. Capture `EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS)` for the dashboard, latest-history, due-check, search and programming hierarchy queries using production-like cardinality. Redact values and do not run write plans on production.
3. Add only validated composite/partial indexes from section 4, one change at a time; measure read improvement, index size, insert/update cost and cache effects.
4. Configure slow-query logging (`log_min_duration_statement`) and `auto_explain` cautiously in a non-production or sampled environment. Add application query timing and query-count telemetry without logging athlete content.
5. Set a per-request `statement_timeout` below the external request budget and a shorter `lock_timeout`; use separate, deliberate values for migrations and background/admin work.
6. Validate autovacuum/analyze health and bloat on append/update-heavy check-in tables. Tune per-table thresholds only after observing dead tuples and analyze lag.
7. Size SQLAlchemy/Gunicorn connections against Azure Database for PostgreSQL's usable connection ceiling. There is no explicit engine pool configuration in `portal/__init__.py:36-50`; defaults multiplied by pods × workers can surprise during scale-out. Consider a bounded pool, `pool_pre_ping`, connection recycle appropriate to Azure networking, and PgBouncer if measured concurrency warrants it.
8. Review Azure PostgreSQL compute, storage IOPS/latency, memory/cache hit ratio and connection saturation before changing server parameters. Query and schema fixes precede speculative server tuning.

## 11. AKS and Gunicorn recommendations

### AKS/Helm

- Production requests/limits are explicit at 250m/256Mi and 750m/512Mi, but repository data cannot prove they are right (`flask-app/values-production.yaml:51-57`). Measure CPU throttling, RSS/working set, OOM events, request concurrency and p95/p99 latency per endpoint. Set requests near observed steady demand plus headroom; reconsider a tight CPU limit if throttling appears.
- Production has one replica and autoscaling disabled (`flask-app/values-production.yaml:1,32-35`). This prevents horizontal capacity and leaves rolling/resilience behavior dependent on surge scheduling. After database/session safety and load tests, use at least two replicas for availability and enable HPA on a useful signal; CPU alone may miss database-bound saturation.
- Keep the startup probe's 150-second failure window and separate readiness/liveness roles (`flask-app/values-production.yaml:59-77`). The current `/health` endpoint is intentionally cheap but proves only that Flask can answer (`portal/api/health.py:1-8`). Add a separate readiness check for required dependencies with a strict timeout; keep liveness free of database dependency to avoid restart storms.
- Align ingress/backend timeouts, Gunicorn timeout, graceful termination and client budgets. Current Gunicorn portal timeout is 30 seconds, probe timeout is 2 seconds, pre-stop sleep 10 seconds, and grace period 30 seconds (`Dockerfile:28-31`; `flask-app/values-production.yaml:59-80`). A 30-second in-flight request starting late in pre-stop may exceed the remaining grace period; verify Gunicorn receives/drains termination as expected and shorten application query/request budgets.
- Use migration-specific resources and monitor Pending time, image pull, startup duration and readiness transition. Preserve `maxUnavailable: 0` (`flask-app/templates/deployment.yaml:13-18`).

### Gunicorn

- Two gthread workers × four threads expose up to eight request threads per pod (`Dockerfile:31`). Benchmark this against CPU allocation and database pool/connection limits; eight Python request threads under a 250m request can increase queuing and context switching.
- Move Gunicorn arguments to reviewed configuration so worker/thread counts, graceful timeout, keep-alive, access-log timing and maximum request recycling are explicit. Add `graceful_timeout`, `keepalive`, `max_requests` and jitter only for measured operational reasons, not as latency fixes.
- Record worker boot time and worker timeout/restart counts. Do not increase the 30-second timeout to mask slow queries; set upstream and database timeouts coherently.
- Test worker counts approximately from available CPU and workload behavior, then verify under mixed traffic. Database-bound endpoints may benefit from threads, while Python/Jinja-heavy responses may need processes/CPU; repository inspection cannot choose the optimum.

## 12. Measurement plan

### Baseline

1. Define production-like dataset tiers: athletes; blocks per athlete; weeks per block; sessions per week; prescriptions per session; weekly and nutrition check-ins per athlete; exercises. Use generated, non-personal data and publish counts, not claimed production counts.
2. Instrument Flask request count/duration by normalized route, status and method; Gunicorn queue/worker behavior; SQL query count and cumulative SQL duration per request; response bytes; and template render time. Avoid athlete IDs or free text in metric labels.
3. Capture PostgreSQL calls, total/mean execution time, rows, buffer hit/read, temporary bytes, locks, connections, transaction duration and deadlocks. Correlate with request traces using safe identifiers.
4. Record AKS CPU use/throttling, memory working set, restarts/OOMs, pod readiness/startup, HPA state, network and ingress duration; record Azure PostgreSQL CPU, active connections, IOPS and storage latency.
5. For browser paths, collect navigation timing, TTFB, LCP, INP, CLS, transferred bytes, request count and main-thread long tasks. Run cold-cache and warm-cache variants.

### Query verification

- Add query-count regression tests for `/check-ins`, `/programming`, block detail, and week editor at multiple hierarchy sizes. Expected query count should remain constant or deliberately bounded.
- Save sanitized plans for each candidate index before/after using the same dataset and warmed/cold-cache protocol. Compare planning time, execution time, actual/estimated rows, sort method, buffer reads and writes.
- Measure allocations/RSS and serialized HTML size for dashboards; query time alone will miss Python aggregation and rendering cost.

### Acceptance method

Establish service-level targets from current user needs and measured baseline; none exist in this repository. Report distributions and confidence (median, p95/p99, error rate) rather than a single average. Repeat tests, document environment, dataset, commit, pod shape, PostgreSQL tier, cache state and background load. Treat Playwright functional timeouts as failure guards, not latency targets.

## 13. Load-test scenarios

Run against a disposable performance environment with production-like PostgreSQL and AKS configuration, never against live athlete data.

1. **Coach morning burst:** concurrent `/coach`, `/check-ins`, `/nutrition`, `/athletes` and `/programming` reads with a mix of cold and warm caches. Watch query count, dashboard Python time, DB connections and response bytes.
2. **Athlete check-in deadline:** authenticated athlete dashboard, check-in form, duplicate validation and submission bursts concentrated around one check-in day. Verify uniqueness under concurrent double-submit, lock time and write latency.
3. **Nutrition review:** coach nutrition dashboard plus athlete nutrition submissions and coach responses. Include long histories to expose full-history scans.
4. **Programming edit:** view block/week/session, create/update/delete prescriptions, duplicate sessions/weeks/blocks, and extend a maximum-sized block. Track N+1 reads, flush count, transaction duration and lock contention.
5. **Exercise discovery:** movement-only, common contains term, rare term, no-result term, long input, and paginated traversal. Compare sequential scan, trigram/full-text candidates and result rendering.
6. **Static/public traffic:** guide page cold load, repeat load, image delivery and Chart.js history page. Test cache headers, compression, CDN/ingress behavior, transfer bytes and browser metrics.
7. **Scale and failure:** ramp to saturation, hold steady, spike, and recover while deleting a pod or rolling a deployment. Verify readiness, connection surge, graceful termination and error rate.
8. **Migration rehearsal:** restore a production-shaped sanitized backup, apply migrations, measure DDL duration/locks/WAL/resource use, then start/roll pods. This is separate from request load.

Include a low-rate mixed workload for soak testing to reveal connection leakage, memory growth, bloat and worker recycling behavior. Never infer capacity from Playwright.

## 14. Prioritised quick wins

| Priority | Work | Why | Schema change? |
|---|---|---|---|
| P0 | Add eager loading/view-model queries to the four confirmed rendered N+1 paths. | Removes query growth with block/week/session/check-in count. | No |
| P0 | Paginate global check-ins, exercise results, programming block lists and athlete histories; cap dashboard sections. | Bounds DB, Python, HTML and browser work. | No, though supporting indexes are recommended separately |
| P0 | Push coach-dashboard date/status/review filters into SQL and fetch only displayed/latest rows. | Stops lifetime-table reads on the highest-fan-out page. | No |
| P1 | Bound nutrition dashboard history and derive latest/recent rows in SQL. | Removes complete-history materialization. | No |
| P1 | Remove unused/all-row fetches, notably all athletes on programming index where only blocks are rendered. | Immediate reduction in objects/query work. | No |
| P1 | Optimize and dimension the 650,839-byte logo; add intrinsic dimensions and measured caching/compression. | Clear public-page transfer/layout improvement. | No |
| P1 | Add request/query timing, query-count tests and sanitized PostgreSQL plan capture. | Makes all subsequent changes evidence-driven. | No |
| P2 | Defer/self-host Chart.js and load only page-specific operations CSS. | Reduces blocking/unused assets; browser-measure first. | No |
| P2 | Batch existing-row lookups and reduce flushes in explicit seeds/factories. | Helps admin paths; lower user impact than read-path work. | No |

## 15. Work requiring schema changes

- Add and validate composite/partial indexes listed in section 4 through Alembic migrations.
- Enforce weekly-check-in uniqueness on `(athlete_id, week_ending)` after auditing existing duplicates and defining conflict behavior.
- Add `pg_trgm`, full-text search columns/indexes, `citext`, or normalized-name indexes if chosen for exercise search semantics.
- Add programme timing/current-week fields if “ending soon” must be queried efficiently; current code explicitly says dates/current-week markers do not exist (`portal/services/coach_dashboard.py:128-135`).
- Introduce denormalized summary/materialized-view tables only if measured SQL/window-query approaches remain inadequate. Such structures require freshness, transaction and rebuild designs.
- Partition check-in/history tables only at proven large scale; current repository evidence does not justify it.

Every schema item requires migration rehearsal, rollback/forward-fix planning, lock assessment, and before/after plans.

## 16. Work safe for Version 1.0.1

Subject to normal review and regression testing, the following are code/config-only and do not require schema migration:

- eager-load the confirmed lazy relationship paths;
- add conservative pagination and stable ordering to unbounded lists, preserving first-page behavior and links;
- move coach dashboard predicates and limits into existing-column SQL;
- restrict nutrition calculations to the records actually shown/needed;
- remove unused all-row queries;
- optimize the logo and add intrinsic image dimensions;
- add `defer`/SRI or self-host the pinned Chart.js dependency after browser validation;
- add query-count tests, request/query telemetry and a repeatable load-test harness;
- make Gunicorn logging/timing and graceful settings explicit without increasing concurrency until measured;
- add a dependency-aware readiness endpoint while leaving liveness cheap, provided its timeout and failure behavior are tested.

Index additions, uniqueness constraints, extensions, new programme fields and database search structures are **not** classified as Version 1.0.1-safe here because they require schema changes.

## 17. Evidence index and limitations

### Principal files inspected

- SQLAlchemy models and relationships: `portal/models/athlete.py`, `portal/models/checkins.py`, `portal/models/nutrition_checkin.py`, `portal/models/programming.py`, `portal/models/exercise_library.py`.
- Dashboards/check-ins: `portal/services/coach_dashboard.py`, `portal/services/athlete_dashboard.py`, `portal/services/nutrition_dashboard.py`, `portal/services/checkins.py`, `portal/checkins.py`, `portal/athletes.py`.
- Programming: `portal/programming_routes/*.py`, `portal/programming_services/*.py`, `portal/programming_templates.py`, and `templates/programming/*.html`.
- Search: `portal/exercise_library.py`, `templates/exercises/index.html`.
- Startup/database/seed: `portal/__init__.py`, `portal/database_config.py`, `portal/api/health.py`, `portal/seed_programming_engine.py`, `portal/database_cli.py`, `Dockerfile`.
- PostgreSQL schema: `migrations/versions/0001_baseline_coaching_schema.py`, `migrations/versions/0002_add_exercise_knowledge_columns.py`.
- Templates/assets: `templates/base.html`, `templates/coach/base.html`, `templates/public/base.html`, `templates/checkins/*.html`, `templates/nutrition/index.html`, `static/`.
- AKS/Gunicorn/probes: `flask-app/values.yaml`, `flask-app/values-production.yaml`, `flask-app/templates/deployment.yaml`, `flask-app/templates/migration-job.yaml`, `platform-portal/Dockerfile`.
- Browser timing configuration: `playwright.config.ts`, `e2e/tests/*.spec.ts`, `e2e/support/seed_database.py`, `e2e/support/run_server.py`.

### Limitations

This audit is static and repository-grounded. It does not claim current production row counts, latency, throughput, cache ratios, query plans, Azure PostgreSQL configuration, ingress/CDN behavior, connection ceilings, pod utilization, or user concurrency. The repository contains functional Playwright timeout settings—30-second test, 5-second assertion, 10-second action, 15-second navigation, and 60-second server startup (`playwright.config.ts:13-30`)—but no browser performance budgets or benchmark results. Recommendations that depend on scale are therefore measurement priorities, not confirmed capacity conclusions.
