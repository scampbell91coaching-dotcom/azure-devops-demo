# Organisation ownership domain

The organisation tables are an additive tenancy boundary. Authentication remains
global and unchanged: existing `users` and `athletes` rows do not require an
organisation, and no current route is switched to membership-based authorization.

Membership roles (`owner`, `admin`, `coach`, and `support`) describe staff access
inside one organisation. Membership and coach-athlete ownership have independent
active/inactive lifecycle state so historical rows need not be deleted. Invitations
retain terminal accepted, revoked, or expired states; only one pending invitation
per normalized email and organisation is allowed.

Composite foreign keys prevent an ownership or invitation from naming a membership
from another organisation. All future tenant-aware queries must begin with an
authorized `organisation_id`; athlete IDs and membership IDs alone are not tenant
authorization.

## Later backfill

A separate, reviewed data migration may create one default organisation, add each
existing coach user as an owner or coach membership, and add ownership rows for the
existing athletes. It must define the legacy coach selection explicitly and be
idempotent. This schema migration deliberately does not infer ownership or mutate
production data. Only after that backfill and tenant-aware authorization are shipped
should organisation membership become mandatory in application paths.
