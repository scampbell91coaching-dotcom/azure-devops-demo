# Support/admin security foundation

The platform has no god-mode role. Existing coach and athlete users receive no
support capability. A support adapter must authenticate a separate active
`support_principals` record and load a non-revoked, exact capability grant for
each action. The domain policy fails closed and delegated sessions cannot start
further support actions.

Every sensitive read, delegation transition, suspension, and reactivation must
first be authorised with a non-empty reason and external ticket/reference, then
write an append-only `support_access_events` row. The business mutation should
occur in the same database transaction as its event. If durable audit storage
is unavailable, the action must fail. Event details must be allowlisted and
must not contain secrets, credentials, health data, or raw request bodies.

`tenant_ref` is intentionally opaque because the production schema does not yet
have a real tenant relation. During the single-coach migration it may resolve
server-side to `coach:<user id>`. It must never be accepted as authorization
evidence from a browser. Before multi-coach rollout, introduce a stable tenant
table and membership resolver, backfill one tenant for each legacy coach, map
their existing data, then translate these references without changing event
history. No support route should ship before that resolver exists.

Events default to tenant-visible. A future tenant audit view should show time,
action, support identity label, reason/reference, and affected account, scoped
by the authenticated tenant resolver. `internal` visibility is reserved for a
documented security/privacy exception; it must not become the default or hide
account-state changes and delegation from tenants.

Delegation is optional and disabled until an adapter is built. Starts require
the dedicated capability, a target account, an audit event, and a timezone-aware
expiry no more than one hour away. Sessions must carry the delegation ID, show a
persistent support banner, prohibit delegation chaining, expire server-side,
and generate an end/expiry event. They must not copy passwords, MFA state, or
long-lived user sessions.

Suspension/reactivation requires `support:change_account_state`, an exact target
resolved inside the same tenant, reason/reference, and a tenant-visible event.
Adapters must distinguish tenant account state from individual login state,
require step-up authentication or approval according to operational policy,
make transitions idempotent, and avoid deleting data. This foundation exposes
no routes and changes no current coach workflow or account behavior.
