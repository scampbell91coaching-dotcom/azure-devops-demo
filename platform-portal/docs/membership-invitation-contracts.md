# Membership invitation contracts

These contracts add the SaaS membership boundary without changing the existing
coach UI or athlete account-token flow. Email delivery is intentionally absent.

## Trust boundary

- An issuer must have an active coach membership in the requested organisation.
- An athlete must already belong to that organisation through
  `organisation_athletes`; guessed athlete IDs from another tenant are rejected.
- Acceptance takes only a raw token and authenticated user ID. Organisation,
  role, and athlete linkage come from the persisted invitation, so request IDs
  cannot switch tenant or elevate role.
- The authenticated user's normalized email, legacy role, and (for athletes)
  athlete linkage must match the invitation.

## Token lifecycle

Raw tokens contain at least 32 characters of cryptographic entropy and are
passed once to `InvitationDeliveryAdapter`. Only a SHA-256 digest is persisted;
the random token's entropy, not secrecy of the database digest, prevents offline
guessing. Tokens have a fixed expiry and an atomic pending-to-accepted claim.

Issuing or resending supersedes all matching pending invitations and creates a
fresh token. Revocation is terminal. Accepted, revoked, superseded, and expired
tokens cannot be used. Provider delivery should be implemented later behind the
adapter; issuance is committed before adapter invocation so a provider outage
does not erase lifecycle/audit evidence.

## Audit and migration

Issue, supersede, revoke, and accept events are append-only records containing
the invitation, organisation, actor, action, and timestamp. Tokens and token
digests are not copied into audit metadata.

Migration `0020_membership_invites` creates one stable legacy organisation and
backfills every existing athlete ownership anchor and user membership. This
preserves current single-coach behavior while later route/repository work adopts
membership authorization incrementally.
