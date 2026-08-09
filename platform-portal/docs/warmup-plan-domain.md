# Warm-up plan domain and persistence seam

`portal.services.warmup_plans` models the spreadsheet workflow as a pure domain
service. It does not create tables, import ORM models, or write application data.

The ordered phases are general preparation, athlete-specific intervention,
lift-specific preparation, and barbell ramp-up. Work sets remain owned by the
existing exercise-prescription/session domain and follow the resolved plan.

Protocols are immutable, reusable, versioned templates. Their scope can require
a lift family, explicit athlete IDs, coach-assigned athlete tags, and session
tags. An empty constraint means “all”. Matching never infers a diagnosis or an
exercise intervention: the adapter must only provide context explicitly recorded
by the coach or session workflow.

`WarmupPlanService.build()` combines all matching active protocols. Phase is the
primary ordering invariant; protocol priority, protocol ID, template step order,
and version provide deterministic ordering. Every materialised step records its
protocol ID/version. Manual removal, replacement, and append operations require
an ID, actor, and reason; replacements retain the prior provenance as a parent.

## Later database integration

Implement `WarmupProtocolRepository.list_active()` in an infrastructure module
and map database rows to `WarmupProtocol` values. Keep transaction handling and
ORM entities outside the domain module. The expected persistence aggregate is:

- protocol identity, display name, version, priority, active state, and scope;
- ordered steps containing phase, stable key, instruction, and notes;
- assignment/context data that supplies athlete ID/tags, session ID/tags, and
  the lift family already represented by `ProgrammingLiftSlot`;
- immutable manual override events with target key, action, replacement value,
  actor, reason, and timestamp;
- optionally, a resolved-plan snapshot for historical session fidelity.

Database uniqueness should protect `(protocol_id, version, step_key)` and step
order within a protocol version. A saved session should reference or snapshot a
specific protocol version; it must not silently change when a reusable protocol
is edited. Adapters should reject malformed rows by constructing the domain value
objects, whose validation is the shared boundary.

Until that adapter exists, `InMemoryWarmupProtocolRepository` can be populated
from reviewed application configuration. The service API remains unchanged when
persistence arrives.
