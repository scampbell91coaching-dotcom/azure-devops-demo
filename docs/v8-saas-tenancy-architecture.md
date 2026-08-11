# V8 SaaS tenancy architecture

Status: proposed design; read-only audit of commit `7d77bdc`  
Scope: application tenancy, ownership, authorization, billing boundary, migration,
and verification. This document does not authorize a migration, deployment, or
cluster change.

## Executive decision

Use a shared application and shared PostgreSQL database with **organization ID
on every tenant-owned row**, enforced in three layers: an authorization policy
service, tenant-qualified repository queries, and PostgreSQL row-level security
(RLS) plus composite foreign keys. An organization is the customer, security,
data-export, retention, and future billing boundary.

Users are global identities. They receive permissions through organization
memberships. An athlete profile belongs to exactly one organization in V8 and
may have one or more assigned coaches within that organization. A coach may
belong to several organizations, but must select an active organization and can
never infer access merely from having the global `coach` role.

This closes the present critical gap: at `7d77bdc`, `users.role` contains only
`coach` or `athlete`, coaches have no organization or athlete assignment, and
the central request guard permits every authenticated coach to every protected
route. Path-level athlete checks protect athletes from each other, but not one
coach's data from another coach.

There is also a baseline contract discrepancy to resolve before migration:
`portal/auth.py` includes `nutrition_imports.preview` and
`nutrition_imports.commit` in `_ATHLETE_ENDPOINTS`, while the V7.9 authorization
matrix says these mutations were removed and are coach-only. The route itself
checks ownership and nutrition service state, but not coach role. Product and
security owners must choose the intended rule, update code and matrix together,
and add a regression test; tenancy work must not accidentally preserve an
undocumented permission.

## Goals and non-goals

Goals:

- make cross-organization reads and writes impossible by default;
- give ownership rules a single, reviewable vocabulary;
- preserve athlete self-service and coach collaboration;
- provide a stable organization boundary for subscriptions and entitlements;
- migrate existing data without an unsafe flag day;
- retain shared exercise knowledge and operational telemetry where appropriate;
- make tenant isolation testable at route, service, query, and database levels.

Non-goals for V8:

- database-per-customer or schema-per-customer deployment;
- delegated reseller hierarchies, cross-organization athlete profiles, or
  athlete marketplace discovery;
- implementation of payments, invoices, tax, or pricing;
- replacing session authentication with a new identity provider;
- using RLS as the only authorization layer.

## Domain and ownership model

### Organization

`organizations` is the root aggregate and durable tenant key.

Suggested fields: `id` (UUID), `slug`, `display_name`, `status`, `created_at`,
`updated_at`, `data_region`, and optional `billing_email`. IDs are opaque and
never accepted as proof of access. Slugs are presentation identifiers, not
authorization identifiers.

Lifecycle states should be `provisioning`, `active`, `suspended`, and `closed`.
Suspension blocks normal mutation and current-service delivery, but preserves
owner/admin access to billing, export, and recovery surfaces. Closure is a
retention workflow, not an immediate cascade delete.

### Global user and organization membership

Keep `users` as a global login identity: `id`, normalized globally unique
email, credentials, active state, and authentication metadata. Remove its
global authorization meaning over time.

Add `organization_memberships`:

| Field | Contract |
|---|---|
| `id` | Opaque membership ID |
| `organization_id` | Required tenant FK |
| `user_id` | Required global user FK |
| `role` | `owner`, `admin`, `coach`, or `athlete` |
| `status` | `invited`, `active`, `suspended`, or `removed` |
| timestamps / inviter | Audit provenance |

Required constraints are unique `(organization_id, user_id)`, at least one
active owner per active organization (transactionally enforced), and no
authorization for non-active memberships. A user may have memberships in
multiple organizations. A request has exactly one active membership.

Role meanings:

- `owner`: organization lifecycle, member administration, billing, export, and
  all coaching permissions;
- `admin`: member administration and all coaching permissions, but no ownership
  transfer or destructive organization lifecycle action;
- `coach`: coaching-domain access, limited to assigned athletes unless the
  organization explicitly grants a future `coach_all_athletes` capability;
- `athlete`: read/write only the self-service surfaces belonging to the athlete
  profile linked to that membership.

Do not encode evolving permissions in route-local role conditionals. Resolve
roles to named capabilities such as `athlete.read`, `programming.write`,
`members.manage`, and `billing.manage` in one policy module.

### Athlete ownership and coach assignment

`athletes.organization_id` is required. Add
`athletes.membership_id` as an optional unique FK to an athlete-role membership;
it is null before account activation. The membership and athlete must have the
same organization. An athlete profile is therefore organization-owned even
before it has login credentials.

Replace the authorization significance of `users.athlete_id`; retain it only
temporarily during migration. The canonical self relationship is membership to
athlete profile.

Add `coach_athlete_assignments` with `organization_id`, `coach_membership_id`,
`athlete_id`, `status`, `starts_at`, `ends_at`, and audit provenance. Both ends
must match `organization_id`. Multiple active coaches are allowed so coverage,
specialists, and handover work without transferring ownership. Assignment
grants coaching access; it does not move the athlete or permit membership
administration.

### Resource ownership

Ownership is transitive but must also be materialized. Every tenant-owned table
stores a non-null `organization_id`, even where the organization can be reached
through `athlete_id` or another parent. This deliberate redundancy enables RLS,
partitioning, efficient indexes, unambiguous jobs, and composite foreign keys
that prevent a child in organization A from referencing a parent in B.

For example, `training_sessions` stores `organization_id` even though its block
does. Its FK is `(organization_id, week_id)` to the tenant-qualified parent.
Likewise a warmup assignment binds `(organization_id, athlete_id)` and
`(organization_id, session_id)`. Application validation alone is insufficient.

Tenant-owned IDs may remain globally unique. All lookups must still use
`(organization_id, id)`; global uniqueness is not authorization.

## Request and authorization contract

### Tenant resolution

Resolve organization only after authentication, preferably from a canonical
route such as `/orgs/<org_slug>/...` or a server-maintained active-membership
session value. Validate the selected organization against an active membership
on every request. Host names and headers may assist routing but never establish
authority.

Create an immutable request context containing `user_id`, `organization_id`,
`membership_id`, role/capabilities, and, for athlete members, `athlete_id`.
Background jobs receive the same values explicitly in their payload; they must
not use a process-global tenant variable.

### Policy sequence

Every protected operation follows the same order:

1. Authenticate the global user (`401` or browser login redirect if absent).
2. Resolve and validate the active organization membership (`404` for an
   organization outside the user's memberships).
3. Check the named capability (`403` when the membership lacks it).
4. Load the target with `organization_id` in the query.
5. For coach-to-athlete operations, require an active assignment (or an
   explicitly authorized organization-wide capability).
6. For athlete operations, derive `athlete_id` from the membership; never trust
   a path, form, upload, or session hint.
7. Apply service entitlement and lifecycle rules.
8. Mutate with CSRF protection, optimistic concurrency/idempotency where
   appropriate, and an audit event.

Return `404` for an object absent from the authorized tenant/athlete scope so
existence is not disclosed. Return `403` for a known operation that the active
membership cannot perform. Keep `409` for stale, replayed, or history-locked
state transitions and `400` for malformed input/CSRF.

### Database defense

At transaction start, set a transaction-local PostgreSQL setting such as
`app.organization_id` from the validated request/job context. RLS policies on
tenant tables require `organization_id = current_setting(...)::uuid` for both
`USING` and `WITH CHECK`. The runtime application role must not own the tables,
have `BYPASSRLS`, or use a connection whose tenant setting survives transaction
boundaries. Use `SET LOCAL`, explicit transactions, and reset-on-checkout as a
defensive measure.

Migrations, controlled support tooling, and cross-tenant operational analytics
use separate database roles and audited workflows. Do not silently disable RLS
inside ordinary services or tests. SQLite can remain a developer convenience,
but PostgreSQL integration tests are mandatory because SQLite cannot validate
RLS.

### Service and repository boundaries

Introduce `TenantContext` as a required argument to tenant-aware services and
repositories. Prefer methods shaped like
`get_athlete(context, athlete_id)` and
`list_training_blocks(context, athlete_id)`; ban raw model `.query.get(id)` in
request-facing code. Nested resources must be loaded through a tenant-qualified
parent or with all owning keys in one query.

The policy service answers authorization questions. Repositories enforce query
scope. Domain services enforce workflow invariants and entitlements. Routes
translate HTTP only. This separation prevents the current pattern where a
global request allowlist and scattered route checks carry most of the security
burden.

## Data classification and table migration map

The following inventory reflects ORM tables at `7d77bdc`.

### Direct tenant scope required

Add non-null `organization_id`, tenant-qualified indexes, unique constraints,
and composite foreign keys to:

| Root / area | Tables |
|---|---|
| Identity and athlete | `athletes`, `account_tokens`, `client_service_changes` |
| Check-ins and state | `athlete_checkin_settings`, `weekly_checkins`, `nutrition_checkins`, `athlete_state_facts`, `coach_technical_observations`, `athlete_constraint_flags`, `athlete_state_signals`, `athlete_state_recommendations`, `athlete_state_overrides` |
| Programming | `training_blocks`, `training_weeks`, `training_sessions`, `programming_lift_slots`, `exercise_prescriptions`, `training_session_logs`, `training_set_results` |
| Nutrition integration | `nutrition_provider_connections`, `nutrition_import_jobs`, `daily_nutrition` |
| Meet day | `meets`, `meet_entries`, `meet_lifts` |
| Warmups | `warmup_protocols`, `warmup_protocol_steps`, `warmup_assignments`, `warmup_overrides`, `warmup_plan_snapshots`, `warmup_plan_snapshot_steps` |

`warmup_protocols` should be tenant-owned by default because coach-authored
protocols are customer IP. If system protocols are needed, model a separate
immutable global catalogue (or explicit `scope = system|organization`) instead
of nullable tenant keys. Derived child rows still receive `organization_id`.

All current uniqueness rules that express customer business identity must add
the tenant key. Examples include athlete email, programming positions,
nutrition source/day, warmup stable key/version, and session snapshots. Decide
explicitly whether athlete email may repeat across organizations; the proposed
contract allows it on `athletes` while keeping login email globally unique on
`users`.

### Shared/control-plane tables

Keep these global unless product requirements change:

- `users`: global identity, not global authority;
- `exercises`, `day_templates`, `day_template_exercises`: curated system
  catalogue. Organization customizations should be new tenant-owned override or
  custom-item tables, never edits to shared rows;
- `platform_snapshots`: operational control-plane telemetry, unavailable to
  ordinary tenant roles.

### Acquisition data

`lead_captures` and `coaching_applications` are pre-tenant acquisition records.
They need an explicit `acquisition_owner_id` or destination organization before
the application supports multiple branded funnels. They must not be visible to
every coach. On conversion, copy/link them to one organization via an audited,
idempotent workflow. Until then, restrict them to platform operators or a
designated acquisition organization.

### New control tables

Add `organizations`, `organization_memberships`,
`coach_athlete_assignments`, and `organization_audit_events`. Add billing tables
only when billing is implemented, as described below. Audit events should
capture actor user/membership, organization, action, target type/ID, request or
job correlation ID, outcome, and timestamp without copying sensitive payloads.

## Route and service migration map

### Tenant-scoped coaching surfaces

The following current route families must require organization context and
tenant-qualified resource loading:

- `/athletes...`, athlete dashboard/programme/session, account invitation,
  services, nutrition check-ins, and weekly check-ins;
- `/programming...`, Block Factory, programming APIs/templates, exercise
  prescriptions and lift-slot/session/week/block mutations;
- `/meet-day...` including entries, lifts, warmups, and calculators when a
  persisted meet is involved;
- `/nutrition...` and `/athletes/<id>/nutrition-import...`;
- `/coach`, `/applications...`, and coaching dashboards;
- `/attempt-selection...` whenever athlete/meet state is persisted.

Coach routes must additionally apply assignment scope when their target is an
athlete. List endpoints return only assigned athletes. Object endpoints load by
organization and assignment, rather than loading globally and checking later.
Owner/admin member-management routes are a separate surface.

The athlete-friendly canonical routes without path IDs should remain. They are
safer because identity comes from `TenantContext`. Legacy path-ID athlete routes
may redirect after checking ownership; they must not establish identity.

### Shared and operator surfaces

Public `/apply`, lead magnets, account-token consumption, login, and health
remain outside a tenant session, but their writes need an explicit acquisition
destination and abuse controls. Exercise catalogue reads may be shared;
organization custom items require overlay queries under tenant context.

`/api/v1/platform`, engineering, history, security, GitOps, observability,
resilience, recommendations, release readiness, and similar infrastructure
views are control-plane surfaces. They must be platform-operator-only, not
implicitly available to an organization coach. Platform operator authority
should be a separate global staff claim and audited break-glass mechanism, not
an organization role.

### Services requiring context

All services that accept or derive `athlete_id`, programming object IDs, meet
IDs, imports, check-ins, warmups, prescriptions, client services, athlete state,
meal plans, holiday mode, training schedules/logs, coach dashboards, or account
lifecycle data become tenant-aware. Repository methods for history and
snapshots must distinguish tenant business history from global operational
history. Cache keys, files/object storage paths, metrics labels, queues, exports,
and idempotency keys include organization ID (metrics should avoid high-cardinality
raw tenant labels unless deliberately controlled).

## Future billing boundary

The billable customer is `organization_id`, never a coach user or athlete row.
This supports staff turnover and multiple coaches without transferring a
subscription. Proposed future entities:

- `billing_accounts(organization_id unique, provider_customer_id unique,
  currency, billing_email, tax metadata reference)`;
- `subscriptions(organization_id, provider_subscription_id, plan_key, status,
  current_period_start/end, cancel_at, version)`;
- `subscription_items` or `entitlements(organization_id, capability, limit,
  effective interval, source)`;
- `billing_webhook_events(provider_event_id unique, received_at, processed_at,
  outcome)` with idempotent processing.

Provider payloads are evidence, not request authorization. Webhooks resolve a
pre-existing provider customer mapping, lock/version subscription state, and
write entitlements transactionally. Normal services read a locally persisted,
time-effective entitlement snapshot; they do not call the payment provider in
the request path.

Keep commercial entitlements separate from membership permissions and athlete
service flags. Authorization is the intersection of organization lifecycle,
membership capability, coach assignment/self ownership, subscription
entitlement, and athlete-specific service state. Billing suspension must not
erase history or block export/recovery paths.

## Migration plan

### Phase 0: inventory and invariants

- Freeze this ownership map as an ADR and enumerate every raw SQL, ORM query,
  background job, CLI command, seed, import/export, and object-store key.
- Add static checks that flag tenant models without `organization_id` and
  request-facing global ID lookups.
- Establish production data diagnostics: orphan rows, conflicting athlete
  emails, invalid nested relationships, duplicate users, and unknown actors.
- Define a rollback criterion for each later phase. Never delete legacy columns
  in the same release that stops reading them.

### Phase 1: additive schema

- Create organization, membership, assignment, and audit tables.
- Add nullable `organization_id` columns and supporting indexes to all mapped
  tenant tables; add new constraints as `NOT VALID` where PostgreSQL permits.
- Create one deterministic legacy organization and owner membership. Do not use
  a generic sentinel organization in steady state.
- Add organization-aware APIs behind a disabled feature flag. Existing behavior
  remains unchanged.

### Phase 2: deterministic backfill

- Backfill athletes to the legacy organization, then descendants in dependency
  order using parent joins, in bounded resumable batches.
- Backfill coach users as memberships and athlete users as athlete memberships;
  create assignments that reproduce the existing single-coach deployment.
- Quarantine ambiguous/orphaned rows rather than guessing. Emit counts and
  checksums per table; require zero unclassified tenant rows.
- Validate every child organization matches every parent organization.

### Phase 3: dual enforcement and shadow verification

- Write organization ID on every new row while continuing legacy reads.
- Shadow-run tenant-qualified reads and compare IDs/counts with legacy results;
  alert on divergence without exposing shadow data.
- Require explicit tenant context in services and jobs. Update caches, exports,
  uploads, and idempotency keys.
- Add composite unique keys/FKs and validate constraints online. Add `NOT NULL`
  only after backfill and write-path proof.

### Phase 4: authorization cutover

- Change request authorization from global user role to active membership,
  capabilities, and assignment/self ownership.
- Introduce organization-qualified canonical routes and safely redirect legacy
  links after authorization.
- Enable tenant-scoped reads/writes per workflow, starting with read-only
  athlete lists and progressing to mutations. Fail closed if tenant context is
  absent.
- Run two-tenant canaries in an isolated non-production environment and review
  denial audit events.

### Phase 5: RLS and cleanup

- Deploy RLS policies and restricted runtime DB roles, first in forced test and
  staging modes, then production after query-plan and pool-leak tests.
- Remove legacy global role authorization and `users.athlete_id` only after at
  least one full rollback window and verified no reads/writes depend on them.
- Remove feature flags and compatibility code. Document tenant export,
  suspension, closure, and incident response.

Rollback means switching reads to the still-maintained legacy path during
Phases 1-4; new writes must remain compatible. Once RLS and destructive cleanup
occur, rollback is a forward repair, so backups and a rehearsed restore are
release gates.

## Failure modes and controls

| Failure mode | Primary control | Expected behavior |
|---|---|---|
| Coach guesses another tenant's athlete/object ID | Membership + assignment policy; tenant-qualified query; RLS | `404`, no existence leak, denial audit |
| Child references parent in another tenant | Composite tenant FK and `WITH CHECK` RLS | Transaction rejected |
| Missing tenant context | Required `TenantContext`; DB setting absent causes RLS denial | Fail closed, never global query |
| Connection-pool tenant leakage | `SET LOCAL`, explicit transaction, checkout reset/test | Next request sees no prior tenant |
| Background job omits or forges tenant | Signed/validated job envelope; membership/system capability; RLS | Job fails/quarantines; no fallback tenant |
| Global cache/object key collision | Organization-prefixed keys and storage paths | No cross-tenant hit/overwrite |
| Coach removed during a long session | Membership/assignment checked from current DB state; short cache TTL/versioning | Next operation denied; session alone is insufficient |
| Nested ID mix-up (job/session/entry from B with athlete from A) | Single tenant-qualified join plus composite FKs | `404` or DB rejection |
| Bulk import/export crosses scope | Organization fixed server-side; row-level validation; manifest counts | Atomic reject/quarantine and audit |
| Billing webhook replay/out-of-order delivery | Provider event uniqueness, locking/version rules, effective intervals | Idempotent state; no entitlement escalation |
| Organization suspended/closed | Central lifecycle policy | Mutations/current delivery blocked; recovery/export retained |
| Shared catalogue edited by tenant | Separate system catalogue and tenant overrides | Shared row remains immutable |
| Support/operator access becomes a back door | Separate staff claim, reason/ticket, time limit, audit | Explicit break-glass only |
| Logs/metrics expose tenant data | Redaction and opaque correlation IDs; controlled labels | No PII or secrets in telemetry |
| Migration assigns orphan to wrong tenant | Deterministic parent backfill and quarantine | Cutover blocked until reconciled |

## Test strategy and release gates

Use at least two organizations (`A`, `B`), two coaches, owner/admin users, two
athletes per organization, an unassigned coach, a multi-organization coach, and
colliding human-readable names. For every tenant-scoped resource and operation,
generate a matrix of own organization/other organization, assigned/unassigned,
role, active/suspended membership, active/suspended organization, entitlement,
and safe/unsafe HTTP method.

Required suites:

1. **Policy unit tests:** capability matrix, membership lifecycle, assignment,
   athlete self derivation, owner invariants, organization lifecycle, and
   entitlement intersection.
2. **Repository/service tests:** every list/get/create/update/delete includes
   organization scope; nested mismatches return not found; caller-supplied
   organization and athlete identity are ignored/rejected.
3. **Route tests:** login/`401`, `403` versus concealed `404`, CSRF, canonical
   tenant selection, multi-membership switching, stale sessions, and redirects.
4. **PostgreSQL RLS tests:** application role cannot select/update/insert/delete
   B while set to A; absent/invalid setting denies; owner/bypass attributes are
   absent; pooled connections and concurrent transactions do not leak context.
5. **Constraint tests:** composite FKs reject cross-tenant parents; tenant
   uniqueness behaves as designed; cascades cannot cross organizations.
6. **Job/integration tests:** imports, exports, account invitations, email,
   webhook replay/order, queue retries, caches, and object paths retain tenant
   scope and idempotency.
7. **Migration tests:** upgrade a realistic `7d77bdc` database, verify row counts
   and checksums, exercise mixed-version writes, validate constraints, and
   rehearse rollback/restore.
8. **Browser tests:** coach A never sees B in lists/search/autocomplete/direct
   URLs; athlete A cannot access athlete B; a multi-org coach sees only the
   selected organization; switching invalidates tenant-specific navigation and
   caches.
9. **Performance tests:** tenant-leading indexes are used, RLS plans remain
   bounded, list pagination cannot scan all tenants, and noisy-neighbor limits
   are observed.

Release gates are zero unclassified rows; zero tenantless writes under shadow
telemetry; complete route/service/table inventory; passing PostgreSQL RLS and
pool tests; passing cross-tenant mutation tests; reviewed query plans; restore
rehearsal; and security sign-off. Existing single-tenant tests remain regression
coverage but are not evidence of isolation when authentication is disabled.

## Acceptance criteria

V8 tenancy is ready only when:

- every business row is explicitly classified as global, acquisition, or
  tenant-owned, with no nullable steady-state tenant key;
- every tenant-owned lookup and mutation is organization-qualified;
- a coach's access is membership- and assignment-based, not global-role-based;
- athlete identity is server-derived from the active membership;
- composite constraints and RLS independently reject cross-tenant writes;
- jobs, caches, files, exports, invitations, and audit events carry tenant
  context;
- billing can attach to an organization without changing resource ownership;
- two-tenant negative tests pass at policy, HTTP, service, and PostgreSQL layers;
- migration reconciliation, rollback, and restore evidence is retained.
