# Self-service SaaS onboarding contract

## Scope and compatibility

This is an additive backend/domain contract. It does not register public HTTP
routes, alter the coach UI, send email, call a billing provider, or switch
existing authorization to tenancy. Existing production behaviour therefore
continues while tenant-qualified adapters and route cutovers are built.

Migration `0020_saas_onboarding_contract` creates one deterministic legacy
organization only when existing users or athletes are present. It links all
existing records, promotes the lowest-ID coach to owner, and marks that
organization's optional coach step skipped and plan `starter`. Where an owner
and athlete exist it is ready immediately. Historical athlete links may have a
null `added_by_user_id` because the actor cannot safely be inferred. If no
coach exists, data is preserved but onboarding remains not ready and requires
operator reconciliation. The migration does not alter `users`, `athletes`, or
any coaching workflow table.

## State machine

| Step | Required | Completion evidence |
|---|---:|---|
| `account_creation` | yes | Active coach who owns the organization |
| `organisation_creation` | yes | Organization and onboarding rows exist |
| `owner_membership` | yes | Active owner membership |
| `coach_invite` | no, but must be resolved | Pending coach invitation created, or explicitly skipped |
| `athlete_add_or_invite` | yes | Tenant-owned athlete link or pending athlete invitation |
| `plan_or_trial_selection` | yes | Allowlisted plan persisted |
| `ready_to_coach` | terminal | Every required step complete and optional step resolved |

Progress is derived from durable evidence rather than a client-supplied step.
`revision` increments on mutations so a future API can support optimistic
concurrency. Steps can be resumed and safely displayed after logout. Readiness
is recalculated after every mutation and timestamped in `ready_at`.

## Validation and authorization

- Organization creation requires an active global coach account. It atomically
  creates its owner membership and onboarding record.
- Every subsequent read or mutation requires the actor's active owner
  membership for the exact organization ID. Callers must never accept a tenant
  ID and query globally before this check.
- Slugs are normalized lowercase and constrained to 80 URL-safe characters;
  organization names, email shape, invite role, and plan codes are allowlisted.
- An athlete has exactly one organization link during this migration phase.
  Attempting to attach an athlete already owned by another tenant is rejected,
  including when the caller owns both tenants.
- An athlete-scoped invitation can only reference an athlete already linked to
  the same organization. Invitations expire after 48 hours and contain no
  bearer token or provider delivery state in this contract.
- Plan selection persists intent only. `trial_ends_at` is deterministic domain
  state; it does not prove payment or grant an entitlement.
- Database constraints are a second line of defence. Route policy,
  tenant-qualified repositories, and eventually PostgreSQL RLS remain required
  before the platform is safe for multiple live customers.

## Future API and UI adapter work

No endpoints are registered by this change. A future versioned JSON API can
adapt to the service with the following owner-authenticated endpoints:

- `POST /api/v1/signup` — create account with email verification and password
  policy; do not disclose whether an email already exists.
- `POST /api/v1/organizations` — create organization and owner membership.
- `GET /api/v1/organizations/{organization_id}/onboarding` — return steps,
  `current_step`, `ready`, and `revision`.
- `POST /api/v1/organizations/{organization_id}/invitations` — create coach or
  athlete invitation; enqueue delivery only after commit through an outbox.
- `POST /api/v1/organizations/{organization_id}/onboarding/coach-invite/skip`.
- `POST /api/v1/organizations/{organization_id}/athletes` — create and link an
  athlete in one transaction, or link through an explicit tenant-aware adapter.
- `PUT /api/v1/organizations/{organization_id}/onboarding/plan` — select trial
  or plan intent using `If-Match`/revision to reject stale writes.
- `POST /api/v1/organization-invitations/{opaque_token}/accept` — digest the
  single-use token, validate expiry/status, then atomically create membership.

The signup UI can be a separate thin client of these endpoints. Existing coach
templates and programming routes should not be reused as an implicit tenant
API or redesigned during this rollout.

## Integration boundaries and rollout

Email delivery should consume invitation records through an outbox and update
delivery metadata without changing onboarding truth. Billing should implement
a provider-neutral adapter such as `start_checkout`, `start_trial`, and
`subscription_status`; webhooks, not redirects, should establish paid
entitlements. Tests must use deterministic fakes.

Before exposing signup publicly: add verified-email/token contracts; add
idempotency keys and rate limits; tenant-qualify athlete creation and every
downstream repository; add coach-athlete assignment policy; introduce
organization selection in sessions; run reconciliation for the legacy backfill;
and complete two-tenant negative tests (including jobs and exports). Only after
those gates should tenant authorization replace the legacy global-coach policy.
