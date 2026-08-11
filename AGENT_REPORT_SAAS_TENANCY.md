# SaaS tenancy design/audit report

## Outcome

Completed a read-only architecture audit against base commit `7d77bdc` and
produced the proposed V8 design in
`docs/v8-saas-tenancy-architecture.md`. No application code, migration, merge,
deployment, or live-cluster action was performed.

## Evidence reviewed

- ORM models and migrations through `0015_client_services`;
- application factory and centralized authentication/CSRF handling;
- athlete, check-in, nutrition import, programming, warmup, meet-day,
  application, API, and dashboard routes;
- programming and coaching services/repositories;
- existing V7.9 authorization matrix and tenancy-relevant unit/E2E tests.

The checked-out branch is one commit after the requested base. Its only diff
from `7d77bdc` is `AGENT_PROMPT.txt`; application code is unchanged. Findings
and recommendations therefore use `7d77bdc` as the source baseline.

## Principal findings

### Critical: coaches are globally authorized

`users` has a global `coach|athlete` role and no organization membership.
`portal.auth._authorize_request` allows any authenticated coach through every
protected route. There is no coach-to-athlete assignment relation. Existing
documentation correctly acknowledges that “coach access currently means any
authenticated coach.” Multi-customer operation on this model would expose one
customer's data to another customer's coach.

### Critical: persisted business data has no tenant key

The audited ORM contains athlete-owned hierarchies but no `organization_id`.
Most isolation is an `athlete_id` filter, sometimes inherited through a parent.
There is no database-enforced tenant boundary, no composite tenant foreign key,
and no RLS. A missed query predicate or mismatched nested ID can therefore
become a cross-customer disclosure or write.

### High: central allowlisting is too coarse for SaaS

The request guard provides useful authentication, CSRF, role separation, and
athlete path-ID concealment. It cannot express membership, selected tenant,
coach assignment, organization lifecycle, or capability. Several services use
global model lookups and assume a coach is an authorized athlete selector.

The baseline also contradicts its own V7.9 authorization matrix:
`nutrition_imports.preview` and `nutrition_imports.commit` remain in
`_ATHLETE_ENDPOINTS`, although the matrix says they were removed as coach-only
mutations. The routes enforce athlete ownership and nutrition enablement but do
not independently require coach role. This needs an explicit product/security
decision and regression coverage before tenancy cutover.

### High: control-plane and acquisition surfaces need explicit owners

Infrastructure/status APIs are protected from anonymous access but are
implicitly coach-accessible. They should be platform-operator-only. Lead
captures and coaching applications occur before an athlete exists and have no
destination organization; they require an acquisition-owner policy before
multiple organizations share the application.

### Medium: existing tests do not prove tenant isolation

There is good coverage for athlete self-ownership, CSRF, role boundaries,
nutrition job binding, warmup history, and programming workflows. Many tests
intentionally disable authentication, and no current suite can prove
organization isolation or PostgreSQL RLS/pool safety because the schema has no
tenant concept.

## Recommended decision

Adopt a shared-database, shared-schema model with organization ID materialized
on every tenant-owned row. Keep users global, authorize via active organization
memberships, link athlete self-service through an athlete membership, and grant
coach access through explicit coach-athlete assignments. Enforce the boundary
in policy, tenant-qualified repositories, composite constraints, and PostgreSQL
RLS.

Make the organization the future subscription/customer boundary. Keep billing
entitlements distinct from membership permission and athlete service flags;
effective access is their intersection.

## Proposed delivery sequence

1. Approve the ownership map and inventory all non-HTTP data paths.
2. Add organization/membership/assignment structures and nullable tenant keys.
3. Backfill one deterministic legacy organization with reconciliation evidence.
4. Require tenant context in services/jobs and shadow tenant-qualified reads.
5. Cut authorization over workflow by workflow with two-tenant negative tests.
6. Validate composite constraints, make tenant keys non-null, and enable RLS
   using a restricted runtime database role.
7. Remove legacy global-role and `users.athlete_id` dependencies only after the
   rollback window and restore rehearsal.

## Deliverables

- `docs/v8-saas-tenancy-architecture.md`: ownership model, isolation layers,
  authorization contract, billing boundary, full ORM table classification,
  route/service scope, phased migration, failure modes, test matrix, and gates.
- `AGENT_REPORT_SAAS_TENANCY.md`: audit evidence, risk summary, and handoff.
