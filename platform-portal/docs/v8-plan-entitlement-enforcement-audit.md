# Plan entitlement enforcement audit

## Scope and current-state finding

This audit covers the Flask route map and application services in this checkout.
There is currently no organization, organization membership, subscription, plan,
storage ledger, PDF export route, or AI provider integration. Authenticated
coaches are global. Consequently, plan enforcement cannot safely be wired until
the tenant context described in the SaaS tenancy audit exists.

The existing `ClientServiceProfile` is a separate, athlete-level delivery
agreement (`training`, `nutrition`, `meet_day`, `video_review`). It must remain
separate from organization billing. Effective permission is:

`authenticated role + tenant membership/assignment + organization plan + athlete client service`

The last term applies only to athlete-specific service delivery. No entitlement
decision may grant tenant access or compensate for a failed ownership check.

## Central contract

All HTTP, job, CLI and service entry points should call one
`PlanEntitlementService`, using `EntitlementRequest(tenant_id, feature, action,
amount, actor_id, resource_id)`. The contract added in
`portal/services/plan_entitlements.py` is persistence and provider independent.
A later adapter should read a local, versioned subscription snapshot; normal
requests must never call Stripe or another payment provider.

Enforce at the service/use-case boundary, with route checks only for early UX
failure. A UI-only check is never sufficient. Tenant authorization must run
first, returning `404` for an inaccessible resource; only then return a stable
`403` entitlement failure. This avoids revealing another tenant's resource or
plan. Do not put raw provider/product/price identifiers in route logic.

Seat and byte limits are concurrency-sensitive. `RESERVE` must count and reserve
inside the same database transaction as athlete/member creation or upload
metadata persistence (row/advisory lock or serializable equivalent). A
check-then-write route implementation can oversubscribe a plan. Background jobs
must re-check before execution, not trust enqueue-time UI state.

## Feature and enforcement map

| Feature | Meter / semantic | Enforcement point |
|---|---|---|
| Athlete counts | Active, non-archived athletes per organization; invitation-only athletes count once persisted | Reserve on `POST /athletes`; onboarding invite does not double count. Define archive/reactivation behavior before launch. |
| Coach/member counts | Active organization memberships, including pending accepted-seat policy | Future member invite/accept/reactivate services. Current `create-user` CLI must become platform bootstrap only, never a tenant seat bypass. |
| Programming | Organization capability; athlete delivery also requires training service | All programming mutations and current programme delivery. Preserve historical programme reads after downgrade. |
| Analytics | Organization capability | Performance/history/recommendation analytics routes and their query services. Keep operational platform telemetry operator-only, not a paid analytics feature. |
| Nutrition | Organization capability; athlete delivery also requires nutrition service | Nutrition prescriptions, check-ins, imports, dashboards, and meal-plan workflows. Historical records remain readable after disablement. |
| Meal-plan PDF | Per-plan capability, optionally metered exports | Future export/render job and download authorization. Current HTML meal-plan routes are nutrition, not PDF. No PDF route exists now. |
| Competition | Organization capability; athlete delivery may also require meet-day service | Attempt selection and every meet-day mutation/current workspace. Historical meet results should remain readable. |
| AI/copilot | Explicit opt-in capability plus usage ledger | Future prompt, suggestion, generation, acceptance and regeneration services/jobs. Existing deterministic Block Factory, rules and recommendations must not be silently relabelled or gated as AI. |
| Storage | Persisted tenant bytes, not filesystem scans on each request | Nutrition upload preview/commit and all future attachment/PDF/artifact writes; reserve before accepting content and release idempotently on deletion/expiry. |
| API access | API credential/scope plus feature-specific check | Every tenant business API. `API_ACCESS` is additive: e.g. performance API requires both API access and analytics. Browser session APIs may be exempt initially, but must still check the underlying feature. |

## Route dependency inventory

The patterns below cover every registered product route in the current Flask
map. Methods are called out where read/write policy differs.

### Seats and organization lifecycle

- `POST /athletes` -> `ATHLETE_SEATS:RESERVE`. `GET /athletes` and
  `GET /athletes/<athlete_id>` require tenant authorization but no count check.
- `/athletes/<athlete_id>/onboarding/*` and `/account/*` do not consume another
  seat, but must confirm the athlete belongs to the tenant. Account invitation,
  reset and revoke routes are not a plan bypass.
- `/athletes/<athlete_id>/services` changes athlete delivery flags, not plan
  features; require membership/assignment and never use it to alter billing.
- Future organization member list/invite/accept/reactivate routes ->
  `COACH_MEMBER_SEATS:RESERVE`; suspend/remove/read do not consume new units.
- `/applications*`, `/apply`, `/guides/<slug>` and `/api/v1/lead-captures` are
  acquisition surfaces. Assign an acquisition owner before multi-tenancy; they
  are not subscriber entitlements.

### Programming

Depend on `PROGRAMMING`: `/programming`,
`/athletes/<athlete_id>/programming`, `/athlete/programme*`, and every route
under `/programming/blocks*`, `/programming/weeks*`, `/programming/sessions*`,
`/programming/prescriptions*`, `/programming/lift-slots*`,
`/programming/block-factory*`, `/programming/factory*`, and
`/programming/api/*`. This includes warm-up protocol/assignment/candidate and
day-template operations. Mutations require the feature now; reads of stored
programmes use downgrade/history policy. Athlete delivery additionally requires
their training client-service flag.

Service dependencies: `programming_services.blocks`, `weeks`, `sessions`,
`prescriptions`, `lift_slots`, `warmups`, `revisions`; `programming_engine`,
`programming_templates`, `block_factory`, `weekly_programming_intelligence`,
`persisted_warmups`, `movement_warmup_candidates`, `warmup_plans`,
`training_schedule`, `holiday_mode`, `exercise_swaps`, and the programme portion
of `client_onboarding`. Shared exercise-library reads can remain baseline;
tenant-authored library writes need a later ownership decision.

### Analytics

Depend on `ANALYTICS`: `/performance`,
`/api/v1/athletes/<athlete_id>/performance/charts`, `/history`,
`/api/v1/history*`, `/recommendations`, `/api/v1/recommendations`, and analytics
panels embedded in `/coach`, `/athlete/dashboard`, and athlete detail. A
dashboard may omit paid panels rather than deny the whole page.

Service dependencies: `athlete_performance`, `coach_athlete_performance`,
`performance`, `performance_charts`, `performance_decisions`,
`training_performance`, `recommendations`, and analytics projections in
`athlete_dashboard`, `coach_dashboard`, `history`, and `nutrition_dashboard`.
Basic access to raw athlete-authored logs/check-ins should follow the product's
downgrade policy and must not become inaccessible accidentally.

### Nutrition, meal plans and storage

Depend on `NUTRITION`: `/nutrition`, all
`/athletes/<athlete_id>/nutrition-checkins*`, `/athletes/<athlete_id>/nutrition-prescriptions*`,
`/athlete/nutrition-targets`, all `/coach/meal-plans*` and
`/coach/meal-plan-*`, and `/athlete/meal-plan*`. Nutrition modules within
`/check-ins*`, athlete dashboards and coach dashboards require the same feature.
New/current activity also intersects with the athlete nutrition client-service
flag; historical prescriptions, assignments and check-ins stay readable.

All `/athletes/<athlete_id>/nutrition-import*` routes require `NUTRITION`.
Preview/upload additionally uses `STORAGE_BYTES:RESERVE`; commit must bind the
reserved object to the same tenant and athlete; disconnect/deletion releases
usage idempotently without making history cross-tenant. The current 10 MiB
request cap is a security limit, not a plan quota.

Service dependencies: `nutrition_prescriptions`, `nutrition_dashboard`,
`nutrition_import.myfitnesspal`, `nutrition_entitlements`, `meal_plans`, the
meal-plan repository/workflow, and nutrition branches of `checkins`,
`athlete_dashboard`, `coach_dashboard`, and `client_onboarding`.
Future PDF render/export/download jobs require `MEAL_PLAN_PDF_EXPORT` plus
`NUTRITION`; generated bytes also count toward `STORAGE_BYTES` if retained.

### Competition

Depend on `COMPETITION_TOOLING`: `/attempt-selection/` and every `/meet-day*`
route, including entry, lift, warm-up, plate-calculator and workflow operations.
New/current athlete-specific work also intersects with meet-day client service;
historical result reads remain available after downgrade.

Service dependencies: `attempt_selection`, `meet_day`, `competition_day`,
`competition_bodyweight`, and `plate_loading`; competition context projected by
`athlete_state`, `athlete_performance`, `calendar_scheduling`, programming and
warm-up services must check the feature before exposing paid competition output.

### Future AI/copilot

No present route or provider call qualifies as AI. Add `AI_COPILOT` at the
future use-case boundary for generation, explanation, chat, regeneration and
acceptance/audit jobs. Gate before external calls, use deterministic provider
fakes in tests, re-check queued jobs, meter idempotently by request key, and do
not send cross-tenant or non-consented athlete context. Deterministic
`/programming/factory*`, coaching rules and recommendations retain current
behavior unless product explicitly creates a separate AI mode.

### API and non-product surfaces

- Tenant business APIs currently registered are the performance charts API and
  programming APIs above. Once external API credentials exist, require
  `API_ACCESS` plus `ANALYTICS` or `PROGRAMMING` respectively, after tenant and
  athlete ownership checks.
- `/api/v1/executive`, `/api/v1/engineering-overview`, `/api/v1/platform`,
  `/api/v1/security`, `/api/v1/gitops`, `/api/v1/observability`,
  `/api/v1/resilience`, `/engineering`, `/infrastructure`, `/security`,
  `/gitops`, `/observability`, `/resilience`, `/release-readiness` are platform
  control-plane surfaces. Restrict them to platform operators; do not sell them
  via organization `API_ACCESS`.
- `/`, `/health`, `/login`, `/logout`, static files and account-token handling
  have no plan dependency. Authentication and recovery must work during billing
  failure. `/coach`, athlete detail, and athlete dashboard are composite shells:
  authorize tenant access once, then gate each paid panel/action independently.

## Persistence and migration handoff

Recommended additive records are organization subscription snapshots, plan
feature grants/limits, immutable billing-sync events, and a tenant usage ledger
with idempotency keys. Store provider customer/subscription/price references in
the adapter, not domain callers. Webhooks authenticate, persist, and enqueue
reconciliation; they do not directly authorize user requests.

For existing single-coach data: create the deterministic legacy organization
and memberships first, backfill tenant keys and one compatibility subscription,
then shadow-evaluate decisions while the legacy allow-all adapter remains an
explicit deployment choice. Reconcile counts and denied-decision logs before
enforcement. Never infer a tenant from the first row, current global coach, or
untrusted request parameter. Make tenant keys non-null and enforce composite
tenant foreign keys/RLS only after two-tenant negative tests pass.

Downgrades should block new mutations and resource growth without deleting
data. Historical programme, nutrition, meal-plan and meet records remain
readable to authorized tenant members. Subscription cancellation, tenant
suspension, user membership, coach-athlete assignment, and athlete service flags
are separate states and require explicit precedence tests.

## Required integration tests

- Two tenants with the same local IDs cannot reuse decisions, cache entries,
  reservations, jobs, downloads or API credentials across tenants.
- Athlete and member seat reservations are atomic under concurrent requests;
  retries with one idempotency key consume once.
- Storage reservation rejects quota overflow before content persistence and
  releases exactly once on deletion/expiry.
- Every direct URL and service invocation denies disabled features even when its
  navigation is hidden; historical-read downgrade behavior remains intact.
- `API_ACCESS` never bypasses the underlying feature or tenant ownership.
- Billing adapter outage uses the last valid local snapshot under a documented
  grace policy and never fails open to an unknown tenant.
- AI tests use a fake provider and prove denial occurs before provider invocation.
