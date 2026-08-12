# PL SaaS security threat model

Status: repository assurance review, 2026-08-12

Scope: the Traditional Strength powerlifting SaaS application only

Deployment authority: none; this review makes no production, Argo, Azure, or
database changes.

## Decision summary

The current snapshot is **not releasable as a multi-tenant SaaS**. The central
request guard in `portal/auth.py` permits every authenticated `coach` to every
protected coach route. Most existing rows and queries are not organisation
qualified. `tests/test_cross_tenant_security.py` demonstrates the resulting
cross-coach IDORs with strict expected failures.

Organisation, invitation, billing, and support tables are useful structural
work, but schema presence is not authorization evidence. They are not yet
wired into a validated request context, tenant-qualified repositories, or
database enforcement. Release must preserve the current single-tenant posture
until blockers RB-01 through RB-06 are closed. Forward repair means adding
scoped paths and backfills before enabling SaaS traffic; it does not mean
weakening the negative contracts or treating expected failures as acceptance.

## Method and classification

The review traced browser requests, sessions, tokens, tenant-owned data,
provider events, privileged support actions, jobs, caches, and lifecycle
operations across trust boundaries. Threats use STRIDE: spoofing (S),
tampering (T), repudiation (R), information disclosure (I), denial of service
(D), and elevation of privilege (E). Severity combines likely SaaS impact and
ease of exploitation; it is not a CVSS score.

Evidence labels are:

- **implemented**: executable application behavior has focused tests;
- **partial**: a useful control exists but is incomplete for SaaS;
- **design/schema only**: no request-to-storage enforcement is evidenced;
- **gap**: the required control is absent or a negative contract exposes it.

## Assets and trust boundaries

Sensitive assets include login sessions and credentials; athlete identity,
bodyweight, nutrition, check-ins, programming and meet data; meal-plan content
and future files; organisation membership and invitations; billing state;
support audit records; exports and deletion state; runtime/migration secrets;
and tenant-bearing job and cache data.

The relevant boundaries are browser to Flask, edge identity hint to application
password authentication, session to active user/membership, route identifier to
repository query, upload/file key to stored object, provider webhook to billing
state, support principal to delegated tenant context, web process to job/cache,
and workload identity to database/SMTP/Key Vault. Edge headers are UX hints,
not authentication evidence. A database row, object key, event ID, or tenant ID
is never proof of authority.

## Threat register

| ID | Area / STRIDE | Threat and impact | Current evidence | Required mitigation / release status |
| --- | --- | --- | --- | --- |
| TM-01 | Auth/session S,E | Stolen, fixed, stale, or disabled-user sessions grant coach or athlete access. | **implemented/partial:** login clears prior session state, checks active users, enforces an eight-hour absolute age, and sets Secure/HttpOnly/SameSite=Lax cookies. No inactivity timeout, server-side revocation/version, or MFA evidence. | Rotate the signing secret safely; invalidate sessions on credential, membership, and support changes; define idle timeout and re-authentication for destructive actions. MFA/IdP assurance decision remains open. |
| TM-02 | Tenant IDOR I,T,E | Any coach enumerates or mutates another organisation's athletes, programming, check-ins, nutrition, performance, or assignments. | **gap:** coach role is globally allowed; strict-xfail route tests expose reads and writes. Organisation tables are **schema only**. | RB-01/RB-02: validated active membership context, tenant-qualified resource loads, assignment policy, non-disclosing 404s, PostgreSQL enforcement, and passing negative matrix. |
| TM-03 | Invitation/token S,I,E | Token leakage, replay, wrong-recipient acceptance, or concurrent consumption activates an account. | **implemented/partial:** 256-bit URL-safe raw token, SHA-256 digest at rest, expiry/revoke/single-use atomic update, email-account binding, fragments keep tokens out of the initial HTTP request, and responses are `no-store`. Organisation invitation acceptance rules are model-only. | Bind organisation invites to active inviter capability and intended normalized email; never log raw tokens; redact mail diagnostics; rate-limit issuance and redemption; test concurrency on PostgreSQL. RB-03 until organisation invite workflow is enforced. |
| TM-04 | Meal plan/file I,T | Direct template/assignment/file IDs disclose another tenant's diet or generated PDF; predictable object keys bypass Flask. | **partial/gap:** draft lookup checks owning coach and athlete history checks athlete ID, but coach list and coach assignment queries are global. No PDF metadata/file-store delivery boundary exists; an expected-failure contract records this. | Tenant-qualified metadata and object keys; authorization before signed URL creation; short-lived download URLs; private storage; content disposition/type controls; deletion propagation. RB-01 and RB-04 before file delivery. |
| TM-05 | Webhook S,T,R | Forged, stale, replayed, or event-ID-colliding webhooks alter subscriptions and entitlements. | **partial/design only:** provider port accepts payload plus signature; domain processor hashes payload and deduplicates `(provider,event_id)`, rejects changed-payload reuse, and retries failed handlers. No HTTP endpoint, real signature verifier/timestamp tolerance, persistent atomic store adapter, body limit, or audit mapping is wired. | RB-05: verify signature over exact raw bounded body before decoding/claiming; reject missing/stale signatures; persistent atomic claim; tenant/customer binding; safe duplicate response; metrics and redacted audit. Never exempt a future endpoint from signature verification merely because CSRF is inapplicable. |
| TM-06 | Support/admin E,R,I | Support self-grants access, selects arbitrary tenant/account, extends delegation, or acts without attributable audit. | **design/schema only:** inactive-by-default principals, capability grants, access events, and expiring delegations exist as models only. Append-only behavior is documentary, not DB-enforced. | RB-06: separate strongly authenticated support identity, approved reason/ticket, least-privilege capability, tenant-visible start/end events, short expiry, no silent renewal, immutable storage enforcement, and prohibition on credential/billing/export impersonation by default. |
| TM-07 | CSRF/redirect S,T | Cross-site writes or open redirects cause account/data changes or credential phishing. | **implemented/partial:** session-bound constant-time CSRF check covers all unsafe methods; login also requires CSRF; redirects reject authority, backslash, control, invalid UTF-8, and repeated encoding. HTML field injection is transitional and API/webhook policy is not separately declared. | Keep global deny-by-default enforcement; add explicit narrowly reviewed webhook exception only with signature verification; retain redirect corpus; migrate forms to explicit tokens. |
| TM-08 | Rate limits D,S | Password spraying, token guessing/issuance abuse, upload abuse, webhook flooding, or export amplification degrades service. | **partial:** login has per-process IP+email window and bounded key count; nutrition upload has a 10 MiB read bound. The limiter is neither shared nor durable and trusts `remote_addr`; other sensitive endpoints lack evidenced limits. | Shared edge/application limits with trusted proxy configuration, account/IP dimensions, exponential backoff, bounded bodies and work queues. Avoid account enumeration and unbounded cardinality keys. |
| TM-09 | Secrets S,I,E | Weak/reused/leaked session, SMTP, OAuth, runtime, or migration credentials enable data access. | **partial:** production refuses missing `SECRET_KEY`; manifests separate runtime and migration URLs and use secret references. OAuth secret lifecycle and DB grants remain external/unverified; Terraform state contains sensitive admin material. | Validate minimum/rotation policy, least-privilege runtime grants, distinct job identities, log redaction, rotation/revocation runbooks, and controlled state/plan access. Never put secret values in cache/job payloads or Helm values. |
| TM-10 | Jobs/cache I,T,E | A worker processes a bare resource ID under the wrong tenant; cache collisions return another tenant's entitlement or data; retries duplicate writes. | **gap/design only:** entitlement request includes tenant ID and rejects mismatched cached decisions. Nutrition import jobs bind athlete ID but execute inline. No general worker/cache adapter or key policy is evidenced. | Every message carries immutable tenant, actor, capability, resource, idempotency key, and schema version; worker re-authorizes and tenant-qualifies loads. Prefix/hash cache keys with environment+tenant+subject+policy version and verify returned scope. Encrypt/authenticate queues and bound retry/dead-letter retention. |
| TM-11 | Export/deletion I,T,R,D | Overbroad export leaks a tenant; deletion crosses tenant boundaries, silently loses audit/billing history, or leaves files/backups/caches behind. | **gap:** no complete organisation export/deletion workflow or retention contract is evidenced. Nutrition disconnect deletes provider rows and clears preview JSON, but is not a full subject/tenant erasure path. | Privileged, re-authenticated, async, tenant-scoped workflow; manifest/count/checksum; encrypted expiring download; approval for organisation deletion; legal-hold/retention rules; tombstone/idempotency; cascade inventory across DB, files, caches, queues, analytics, logs, and backups; auditable completion/failure. |
| TM-12 | Upload/file D,T,I | Malformed archive, decompression bomb, parser exploit, stored filename injection, or retained raw nutrition export leaks/consumes resources. | **partial:** extension/format validation, bounded outer read, filename truncation, and intentional non-retention of raw upload. Expanded archive and parser resource bounds require verification. | Bound compressed and expanded sizes, entry count, row count, CPU/time, nesting and filename handling; parse without active content; quarantine future files; tenant-qualify preview/commit jobs. |

## Release blockers and acceptance evidence

| Blocker | Gate | Minimum evidence to close |
| --- | --- | --- |
| RB-01 | No cross-organisation data plane access | All strict tenant IDOR contracts pass without `xfail`, including list, nested ID, API, nutrition, check-in, programming, meal assignment and future file paths. Queries include validated organisation scope; similar names and guessed IDs disclose nothing. |
| RB-02 | Tenant context and storage enforcement | Active membership is checked per request/job; inactive/switching memberships fail closed. Composite tenant FKs/backfill verification pass. PostgreSQL tests demonstrate `USING` and `WITH CHECK` isolation under the runtime role, including pooled connections. |
| RB-03 | Organisation invitation safety | Issue/revoke/expire/accept endpoints enforce inviter capability, organisation, recipient email, one-time atomic consumption, safe audit/redaction, concurrency, and rate limits. |
| RB-04 | Meal-plan/file isolation | Coach lists and assignment loads are scoped; athlete loads derive identity; private object metadata is tenant-owned; signed download tests cover wrong tenant, expiry, tampering, revocation, and deletion. |
| RB-05 | Webhook boundary complete | Real adapter verifies signature and timestamp on exact bytes, rejects missing/invalid/stale requests, atomically deduplicates persisted events, binds provider customer to organisation, and safely retries without double applying entitlement changes. |
| RB-06 | Privileged support path safe or absent | No generic support access ships. If enabled, capability/delegation lifecycle, expiry, audit immutability, tenant visibility, revocation, and prohibited-action negative tests pass. |

RB-01 and RB-02 are unconditional blockers for any multi-tenant release. RB-03
through RB-06 block release of their respective surface; keeping the route or
feature absent is an acceptable closure for that release. Threats TM-09 through
TM-12 require named owners and accepted operational evidence before production
readiness sign-off.

## Partially automated evidence

Run the repository-only assurance checks from `platform-portal`:

```bash
pytest -q tests/test_security_assurance.py
pytest -q tests/test_auth.py tests/test_account_lifecycle.py \
  tests/test_billing_webhooks.py tests/test_cross_tenant_security.py
```

`test_security_assurance.py` protects stable, non-tenancy invariants and keeps
the blocker register machine-readable. The cross-tenant suite intentionally
retains strict expected failures until implementation closes them. A green run
that reports those expected failures is evidence that the gaps remain
accurately recorded, not evidence of SaaS release readiness.

## Open decisions and review cadence

Security and product owners must decide the organisation context UX, coach
assignment semantics (without adding a second tenant model), support scope,
MFA/step-up policy, export roles and format, retention/legal hold schedule,
webhook provider/tolerance, and shared limiter technology. Re-run this review
when a tenant-owned route/table, file delivery path, external callback, worker,
cache, support capability, or lifecycle endpoint is added. Update the threat
row and its negative test in the same change.
