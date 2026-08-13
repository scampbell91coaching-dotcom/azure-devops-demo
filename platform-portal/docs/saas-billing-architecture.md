# SaaS billing and entitlement boundary

Billing is attached to an organisation, never directly to a coach or athlete.
`subscription_accounts.organisation_id` is unique, so each organisation has at
most one current account. Existing installations receive a deterministic legacy
organisation during migration, but no subscription is created and no existing
authorization decision changes.

## Domain policy

Plan identifiers are stable internal identifiers. The initial catalogue defines
athlete and coach limits plus named capabilities. Unknown plans and capabilities
fail closed. `trialing`, `active`, and `past_due` retain access; `past_due` is an
explicit grace-period policy. `cancelled` and `incomplete` deny access. A future
commercial policy change should alter this domain policy rather than route code.

Entitlement is not authorization. Callers must first establish an
organisation-scoped, authorized principal, then evaluate the subscription for
that same organisation. Counts supplied to capacity checks must come from
tenant-qualified queries. Existing athlete service flags remain a separate,
narrower layer.

## Provider boundary

`BillingProvider` is the port for provider subscription state and signed event
decoding. Domain code stores opaque provider customer/subscription identifiers
and contains no Stripe types. `FakeBillingProvider` is deterministic and does no
network or secret access. A future Stripe adapter belongs at this boundary and
must translate Stripe concepts into the provider-neutral contracts.

Webhook handling first verifies/decodes through the provider adapter, then uses
`WebhookProcessor`. Idempotency is scoped by `(provider, event_id)` and binds the
ID to a SHA-256 payload digest. Successfully processed or concurrently processing
events are duplicates, failed handlers may retry, and ID reuse with changed
content is rejected. The database unique constraint is the durable concurrency
boundary; an integration must implement `WebhookEventStore` transactionally
against `billing_webhook_events` before exposing an HTTP webhook route.

No raw webhook body, payment details, secret, checkout route, or live provider
call is introduced by this foundation.
