# Traditional Strength platform security audit

**Audit date:** 3 August 2026  
**Scope:** repository state at the commit preceding this report  
**Method:** static, repository-grounded review only; no deployment, live probing, secret retrieval, or code/configuration change

## 1. Executive summary

The platform is **not ready to release the private coaching portal through the current production application path**. The principal release risk is architectural: the Flask application has no application-level authentication, coach role enforcement, or general object-level authorisation, yet the production Helm release exposes the complete `app:app` application directly at `traditionalstrength.co.uk`. The separately maintained private-portal ingress does use OAuth2 Proxy, but that protection does not cover the production Flask ingress and it admits any identity in the configured tenant/domain policy rather than an explicit coach group.

The application also has no CSRF protection on numerous state-changing form and JSON routes. Athlete isolation exists only on two athlete-facing dashboard/check-in reads that consume a client-side Flask session value; there is no real login flow that establishes that value, no server-side mapping from an authenticated Entra identity to an athlete, and most athlete-addressed routes trust the URL identifier. Session signing and cookie policy are not configured in the production application factory.

Positive controls include parameterised SQLAlchemy usage, output escaping through Jinja by default, no file-upload surface, non-root containers, dropped Linux capabilities, TLS ingress, private PostgreSQL networking with TLS, generated database credentials stored in Key Vault, workload identity for External Secrets, OIDC for CI cloud access, image/repository scanning, an SBOM, and deliberately isolated Playwright data. These controls do not compensate for the release-blocking identity, authorisation, CSRF, and deployment-boundary gaps.

### Risk count

| Severity | Count | Release effect |
|---|---:|---|
| Critical | 1 | Block release |
| High | 6 | Block release where stated |
| Medium | 8 | Remediate promptly |
| Low | 4 | Hardening/follow-up |

No real secret value is reproduced in this report. Repository identifiers that are not credentials (resource names, tenant/client identifiers, and secret names) are discussed only where needed to identify configuration.

## 2. Confirmed controls already present

- The private hostname uses NGINX external authentication and HTTPS: `private-platform-manifests/ingresses.yaml:29-54`. OAuth2 Proxy uses secure and SameSite=Lax cookies and obtains its client/cookie secrets from a Kubernetes Secret: `private-platform-manifests/private-platform.yaml:102-131`.
- Runtime secret delivery uses an External Secrets `SecretStore`, Azure Workload Identity, and a generated Kubernetes Secret: `kubernetes/external-secrets/azure-key-vault.yaml:1-39`. The Helm Deployment consumes secret keys through `secretKeyRef`: `flask-app/templates/deployment.yaml:59-77`.
- PostgreSQL is private-network-only and requires TLS 1.2 or later: `infra/modules/postgresql/main.tf:26-35,75-85`. Its password is randomly generated and written to Key Vault, and secret values are not Terraform outputs: `infra/modules/postgresql/main.tf:1-9,130-136`; `infra/modules/postgresql/outputs.tf:31-39`.
- PostgreSQL destruction is guarded with `prevent_destroy`: `infra/modules/postgresql/main.tf:64-71`.
- GitHub cloud authentication uses OIDC and job-scoped `id-token: write` in deploy/plan jobs; the top-level application workflow otherwise uses read-only contents permission: `.github/workflows/app-deploy.yml:41-44,179-208,329-341`; `.github/workflows/terraform.yml:20-29,93-106`.
- The application image is scanned by Trivy and fails on fixable high/critical findings: `.github/workflows/app-deploy.yml:159-177`. Repository/IaC scanning and SBOM generation also exist: `.github/workflows/platform-security.yml:59-87`.
- The primary Dockerfile creates and runs as UID/GID 10001; the Helm pod drops all capabilities, forbids privilege escalation, and uses the runtime-default seccomp profile: `platform-portal/Dockerfile:7-24`; `flask-app/templates/deployment.yaml:27-54`.
- ORM lookups and filters are used throughout request paths. The reviewed raw SQL uses static statements with bound parameters rather than request-built SQL, for example `platform-portal/portal/sqlite_postgres_migration.py:186-202` and `platform-portal/portal/models/programming.py:276-281`. No SQL injection was confirmed.
- Jinja templates use normal autoescaping; no `|safe`, `Markup`, or request-driven template construction was found. No file upload endpoint (`request.files`) was found.
- Public coaching applications have a 64 KiB request limit in the dedicated public factory, required-field checks, basic numeric/email validation, consent enforcement, and a honeypot: `platform-portal/public_app.py:24-31`; `platform-portal/portal/coaching_applications.py:54-115`.
- Playwright binds its generated server to loopback, recreates a repository-local disposable SQLite database, uses example-only data, and documents that its fixtures are not authentication: `e2e/support/run_server.py:10-18,31-43`; `e2e/README.md:3-8,33-40`.
- Sensitive logging observed in the application is limited: the coaching application log records only the database identifier, not submitted personal data: `platform-portal/portal/coaching_applications.py:145-151`. Release-evidence tooling includes redaction patterns: `scripts/release/release_evidence.py:20-43`.

## 3. Findings by severity

### Critical

#### C-01 — The production release exposes the full coaching portal without authentication or authorisation

**Affected files/routes:** `platform-portal/portal/__init__.py:28-73` registers every private and public blueprint without an auth hook. `platform-portal/app.py:1-5` exports that application. `platform-portal/Dockerfile:31` runs `app:app`. `flask-app/values-production.yaml:3-21` selects this image and database secret. `kubernetes/ingress/production-ingress.yaml:1-36` routes both public hosts directly to the Flask service with no auth annotations. Representative exposed routes are `/coach`, `/athletes`, `/athletes/<athlete_id>`, `/check-ins`, `/programming`, and all `/programming/api/*` endpoints.

**Impact:** an unauthenticated internet user reaching this ingress can enumerate athlete PII and health/training data and create, modify, review, archive, or delete coaching records. The private OAuth2 Proxy manifests protect a different host/service and therefore do not mitigate this route.

**Remediation:** split public and private deployables at the routing and application registration layers. Deploy `public_app:app` to the public host and make the private host the only route to the coaching app. Add application-level identity verification and deny-by-default route policy so an ingress error cannot expose data. Require an explicit coach role/group for coach routes.

**Verification:** from outside the cluster, assert every private route on the public hosts returns 404 (preferred) or a non-data-bearing denial. Bypass ingress from a test pod and assert private application routes return 401 without a verified identity. With Entra test identities, verify an unauthorised tenant user receives 403 and an authorised coach succeeds. Add a deployment test that renders all ingresses and proves no public host targets the private service.

### High

#### H-01 — No application authentication or coach role model

**Affected files/routes:** no login/logout handlers, auth extension, `before_request`, route decorators, or trusted-header validation exists in `platform-portal/portal/__init__.py:28-93`. Coach-wide reads `/coach`, `/athletes`, `/check-ins`, `/nutrition`, `/programming`, `/exercise-library` and their mutation routes have no identity/role check. OAuth2 Proxy accepts `--email-domain=*`: `private-platform-manifests/private-platform.yaml:105-120`.

**Impact:** even on the private hostname, any identity accepted by the issuer/domain rule can reach coach functions. If the Flask service is reachable through another ingress, port-forward, compromised pod, or future route, there is no second enforcement layer.

**Remediation:** define authenticated principal, coach, and athlete roles; validate a cryptographically trustworthy identity at the app boundary; use deny-by-default decorators/policies; restrict OAuth2 Proxy to an approved Entra group or allow-list; reject direct requests lacking the trusted proxy contract and strip spoofable inbound identity headers at ingress.

**Verification:** unit/integration tests must cover anonymous 401, authenticated wrong-role 403, authorised coach 2xx, deleted/disabled coach denial, spoofed `X-Auth-Request-*` denial on direct service access, and all registered non-public endpoints being classified by policy.

#### H-02 — Athlete isolation is incomplete and URL identifiers authorise cross-athlete access

**Affected files/routes:** only `/athlete/dashboard` and athlete-facing `/athlete/check-ins*` call session-scoped helpers (`platform-portal/portal/athletes.py:25-41`; `platform-portal/portal/checkins.py:32-39,149-169`). In contrast, `/athletes/<athlete_id>`, `/athletes/<athlete_id>/nutrition-checkins/new`, POST `/athletes/<athlete_id>/nutrition-checkins`, `/athletes/<athlete_id>/check-ins/new`, POST `/athletes/<athlete_id>/check-ins`, and `/athletes/<athlete_id>/programming` load the path ID directly (`athletes.py:115-167`; `checkins.py:77-147`; `programming_routes/athletes.py:9-30`). Coach review/settings routes likewise lack coach checks.

**Impact:** insecure direct object references allow one athlete or anonymous caller to read or write another athlete's health, nutrition, and programme records. Guessable integer primary keys make enumeration straightforward.

**Remediation:** map the authenticated subject to exactly one athlete record server-side. Athlete endpoints must derive athlete ID from that mapping, never from a client-controlled session or path; object queries must include the authorised athlete/coach scope. Separate coach-only route namespaces and enforce coach assignment if multiple coaches are supported.

**Verification:** seed two athletes and two coaches. For every read and mutation route, assert athlete A cannot access athlete B by changing every path/body ID; assert coach A cannot access an unassigned athlete; verify 404/403 without revealing record existence; include nested block/week/session/prescription IDs.

#### H-03 — CSRF protection is absent from form and JSON mutations

**Affected files/routes:** there is no Flask-WTF/CSRF dependency in `platform-portal/requirements.txt:1-7`, no CSRF initialization in either app factory, and templates/forms do not have a centrally enforced token. State-changing routes include POST `/athletes`, check-in and nutrition submissions/reviews, exercise create/edit, all programming lifecycle endpoints, PATCH/DELETE `/programming/api/prescriptions/*`, POST reorder, POST `/apply`, and POST `/api/v1/lead-captures`.

**Impact:** a logged-in coach or athlete can be induced by another origin to perform form mutations. SameSite=Lax is not a CSRF control for all browsers, same-site subdomains, compromised sibling origins, or future cookie changes. JSON routes also lack an origin/token policy and could become exploitable as content-type handling evolves.

**Remediation:** enable centrally enforced CSRF protection for browser sessions; add tokens to every state-changing HTML form and require a token/header on JSON mutations. Validate `Origin`/`Referer` as defense in depth. Explicitly document narrowly justified exemptions for anonymous lead/application endpoints and protect those with origin checks, rate limits, and bot controls.

**Verification:** for every mutation, test missing, invalid, expired, and cross-session tokens return 400/403 without a database change; valid tokens succeed; cross-origin form and JSON browser tests fail; anonymous public exemptions remain functional and rate-limited.

#### H-04 — Flask session signing and cookie security are not production-configured

**Affected files/routes:** `platform-portal/portal/__init__.py:36-43` sets database and migration options only; no `SECRET_KEY`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, cookie name, lifetime, or session refresh policy is configured. Athlete routes trust `session["athlete_id"]`: `athletes.py:25-36`; `checkins.py:32-39`. Only tests inject a known key (`e2e/support/run_server.py:31`).

**Impact:** production athlete-session writes cannot safely operate without a strong key. If a weak/default key is introduced operationally, client-side session forgery permits athlete impersonation. Default cookie policy is not an explicit release control, and cookie namespace collisions are possible.

**Remediation:** preferably replace client-selected Flask identity with a verified server-side identity mapping. Regardless, inject a high-entropy rotating Flask secret from Key Vault, fail closed at startup when absent outside tests, set Secure/HttpOnly/SameSite explicitly, choose a host-scoped name, set an appropriate lifetime, and configure trusted proxy handling before relying on HTTPS detection.

**Verification:** production-config startup fails without the secret; two replicas validate the same legitimate cookie; rotation behavior is tested; cookie assertions cover Secure, HttpOnly, SameSite, Path and absence of Domain; a modified cookie is rejected; logout/revocation invalidates access.

#### H-05 — Unbounded/unvalidated mutations permit integrity and resource-exhaustion attacks

**Affected files/routes:** the private factory has no `MAX_CONTENT_LENGTH` (`portal/__init__.py:36-43`). Many text/number fields are stored without length/domain bounds, e.g. athlete creation (`athletes.py:84-105`), prescription JSON (`programming_pack2.py:57-85,90-122`), and exercise create/edit (`exercise_library.py:60-146`). Conversion errors in JSON helpers can become 500 responses. Public `/apply` validates presence/type but not practical field lengths or numeric ranges (`coaching_applications.py:62-143`). No application rate limiting is present.

**Impact:** attackers can generate excessive records or oversized text, cause repeated exceptions, degrade the database/application, and store implausible or unsafe coaching data. Public lead/application endpoints can be spammed despite the honeypot.

**Remediation:** establish request-size limits in both factories and ingress; schema-validate every request with length, range, enum, and type constraints; return consistent 400/422 errors; add database constraints where appropriate; rate-limit anonymous and expensive endpoints.

**Verification:** boundary tests for every schema field; malformed JSON/types never produce 500; oversized bodies receive 413 at ingress and Flask; invalid values do not commit; load/rate-limit tests return 429 without exhausting workers or database connections.

#### H-06 — Key Vault integration does not deliver the `DATABASE_URL` required by the production Helm release

**Affected files:** Helm requires `flask-runtime-secrets/DATABASE_URL`: `flask-app/values-production.yaml:18-21`; both Deployment and migration Job reference it: `flask-app/templates/deployment.yaml:59-66`; `flask-app/templates/migration-job.yaml:36-42`. The committed ExternalSecret creates only `APPLICATIONINSIGHTS_CONNECTION_STRING`: `kubernetes/external-secrets/azure-key-vault.yaml:23-39`. Terraform stores connection components separately rather than a composed URL: `infra/modules/postgresql/main.tf:94-136`.

**Impact:** a clean environment cannot satisfy the documented production contract from GitOps. Operators may create an unmanaged Kubernetes Secret or manually compose a credential-bearing URL, creating drift and accidental disclosure risk; otherwise migration/deployment fails.

**Remediation:** define one reviewed, automated composition/delivery path for `DATABASE_URL` (External Secrets template or a dedicated Key Vault secret), enforce `sslmode=verify-full`, scope access to the workload identity, and document rotation. Do not print or persist the rendered value in CI artifacts.

**Verification:** in an isolated namespace, apply the secret resources and assert the Secret contains both required keys without displaying values; run migration and application successfully; rotate the source credential and confirm controlled refresh/restart; assert logs, events, plans and artifacts contain no URL credential.

### Medium

#### M-01 — Security headers are absent

No app `after_request` policy or ingress header annotations set HSTS, Content-Security-Policy, `X-Content-Type-Options`, `Referrer-Policy`, or clickjacking controls. Affected: both app factories and both production ingress sets. Add headers centrally, begin CSP in report-only mode if needed, and avoid caching pages containing athlete data. **Verify** headers on success, redirect, denial, error, static, and API responses and run CSP/browser regression tests.

#### M-02 — OAuth2 Proxy forwards bearer tokens and identity headers unnecessarily

`--pass-access-token=true` and the ingress forwards `Authorization`: `private-platform-manifests/private-platform.yaml:117-120`; `private-platform-manifests/ingresses.yaml:34-38`. The Flask app does not consume or validate them. This increases bearer-token exposure to application middleware/logging and any compromised pod. Disable token forwarding unless a documented downstream requirement exists; forward the minimum identity claims over a network path inaccessible to untrusted senders. **Verify** upstream requests lack bearer tokens and authentication still works.

#### M-03 — The production container root filesystem remains writable and pod identity is broader than necessary

`flask-app/values-production.yaml:87-89` explicitly leaves `readOnlyRootFilesystem: false`. The Helm pod does not set `automountServiceAccountToken: false` or a dedicated ServiceAccount (`flask-app/templates/deployment.yaml:27-44`). A compromise therefore has more writable/pod-API opportunity than required. Enable read-only root with explicit `/tmp` storage and disable token mounting. **Verify** writes outside declared volumes fail, normal requests/migrations pass, and no service-account token is mounted.

#### M-04 — Network policy protection is inconsistent across release paths

NetworkPolicies exist under `kubernetes/network-policies/` and private manifests, but the `flask-app` chart rendered/deployed by application CI contains no NetworkPolicy template. The direct production service can therefore depend on namespace-global, out-of-chart state. Add deny-by-default ingress/egress plus narrowly scoped ingress-controller, DNS, PostgreSQL, Key Vault/telemetry (as applicable) rules to the release ownership model. **Verify** rendered manifests contain policy and connectivity tests prove only expected flows work.

#### M-05 — Terraform AKS hardening is incomplete

`infra/aks/main.tf:10-56` enables Kubernetes RBAC but does not configure Entra-managed RBAC/Azure RBAC, a private API server, local-account disablement, API authorised ranges, Defender, or automatic node scaling/upgrades. Key Vault CSI secret rotation is disabled at lines 34-36. Establish an explicit cluster threat model and enable applicable controls; do not assume workload identity alone secures the control plane. **Verify** Terraform policy tests and Azure queries for private/authorised API access, disabled local accounts, Entra RBAC, Defender posture, upgrades, and rotation.

#### M-06 — General Terraform security scanning is non-blocking

Checkov uses `--soft-fail` in `.github/workflows/terraform.yml:71-84`, so policy failures do not block apply jobs. The dedicated PostgreSQL scan is blocking (`.github/workflows/postgresql-plan.yml:71-75`), but the general workflow can apply the root and AKS plans on main (`terraform.yml:180-268`). Remove soft-fail or establish reviewed, expiring inline suppressions. **Verify** a fixture violating a required Checkov rule fails CI and prevents plan/apply dependencies.

#### M-07 — CodeQL and repository scanning path filters omit the principal application

CodeQL triggers only for `app/**` and `tests/**`, not `platform-portal/**`: `.github/workflows/codeql.yml:3-16`. Platform Security watches root `Dockerfile` and `requirements*.txt`, not `platform-portal/Dockerfile*` or `platform-portal/requirements.txt`: `.github/workflows/platform-security.yml:3-20`. Thus security analysis may not run when the audited app/dependencies change. Correct path filters or remove them; include Python, workflows, E2E and both Dockerfiles. **Verify** a PR touching each relevant path schedules CodeQL and dependency/IaC scanning.

#### M-08 — Database application credentials appear administrator-scoped and are state-sensitive

Terraform creates one PostgreSQL administrator and stores that password in Key Vault (`infra/modules/postgresql/main.tf:37-38,130-136`); no separate least-privilege runtime/migration roles are provisioned. The generated password also necessarily resides in Terraform state. Provision distinct owner/migrator and restricted runtime roles and tightly control/encrypt/audit remote state. **Verify** runtime credentials cannot create/drop schemas, roles, or unrelated databases; migration credentials are absent from the web pod; state access is limited and logged.

### Low

#### L-01 — Supply-chain references are version tags rather than immutable digests/SHAs

Docker bases (`platform-portal/Dockerfile:1`; `Dockerfile.public:1`), OAuth2 Proxy (`private-platform-manifests/private-platform.yaml:103`), and GitHub Actions are tag-pinned, not digest/full-commit pinned. Pin deployable images by digest and high-trust actions by commit SHA with update automation. **Verify** policy rejects mutable production image/action references.

#### L-02 — Dependency controls are incomplete despite scanning

Python packages are exactly versioned, but installed from an unhashed requirements file (`platform-portal/requirements.txt`); the Playwright dependency permits compatible upgrades (`package.json:11`). Trivy ignores unfixed findings in blocking scans (`app-deploy.yml:170-177`; `platform-security.yml:59-68`). Add hashes/lock generation, dependency review/renovation, and a documented risk-acceptance SLA for unfixed critical issues. **Verify** tampered hashes fail installation and dependency-review policy blocks disallowed severity/licence changes.

#### L-03 — Health and error behavior need explicit information-disclosure tests

`/health` intentionally returns minimal status (`portal/api/health.py:1-8`; `public_app.py:41-43`), which is positive. However, there is no central production error handler or test ensuring exceptions do not disclose stack traces, configuration, database URLs, form bodies, or bearer headers. Add generic error responses and structured redaction. **Verify** forced 400/404/413/500 responses and captured logs contain no PII, cookies, auth headers, or connection strings.

#### L-04 — No upload functionality exists, but no future-upload guardrail is documented

No `request.files`, multipart processing, filename handling, or object-storage upload route was found; this is not a current vulnerability. If uploads are introduced, require allow-listed types verified by content, size/count limits, generated names, storage outside the web root, malware scanning, image re-encoding where relevant, and private download authorisation. **Verify** polyglot, traversal, oversized, executable and cross-athlete download tests before enabling any upload route.

## 4. Authentication and authorisation gaps

The current system has three incompatible notions of identity:

1. The main Flask application has no authenticated principal or coach role.
2. The private ingress authenticates an Entra/OIDC user but Flask neither validates nor maps that user to roles/ownership.
3. Athlete pages trust `session["athlete_id"]`, which is only established by the Playwright-only selector in this repository.

There is no coach-to-athlete assignment model in `platform-portal/portal/models/athlete.py`, and ownership is represented only as `athlete_id` foreign keys on check-ins/programmes. This supports data relationships, not authorisation. A secure design needs a subject-to-user mapping, explicit roles, coach assignment policy, disabled/revoked state, and scoped repository queries. Integer IDs may remain, provided possession of an ID never grants access.

Coach-only route families requiring explicit protection include `/coach`, `/athletes*`, `/check-ins*` (coach views/review), `/nutrition`, `/programming*`, `/exercise-library*`, `/api/v1/executive`, `/api/v1/history`, `/api/v1/platform`, `/api/v1/security`, `/api/v1/gitops`, `/api/v1/observability`, `/api/v1/resilience`, and `/api/v1/recommendations`. Public allow-list candidates are `/health`, `/guides/<slug>`, `/api/v1/lead-captures`, and, in the public app only, `/apply`.

## 5. CSRF assessment

CSRF protection is absent and exploitable once browser authentication exists. Traditional form routes accept ambient-cookie requests without a token. JSON endpoints currently require JSON-shaped requests but have no CSRF token, origin validation, or explicit content-type rejection policy. OAuth2 Proxy's SameSite=Lax cookie reduces some cross-site cases but does not protect same-site sibling origins and does not secure any future Flask athlete session cookie.

CSRF must be enforced centrally rather than route-by-route. Anonymous submissions still need abuse controls; exempting them from CSRF should be an explicit choice because they do not rely on authenticated authority, not an accidental global omission.

## 6. Session and cookie findings

The Flask factory does not configure a production secret or cookie attributes. Flask's signed client-side session is consequently not a suitable source of athlete authority as implemented. OAuth2 Proxy does set Secure and SameSite=Lax but does not explicitly set a short lifetime, refresh policy, cookie domain/path, or HttpOnly in the manifest; defaults should be verified and made intentional. Session revocation, coach logout, athlete logout, fixation resistance, concurrent session policy, key rotation, and multi-replica behavior are untested.

## 7. Secret-management and `DATABASE_URL` findings

No committed real credential was identified by static inspection. GitHub uses secret/variable references and OIDC, Kubernetes uses secret references, and Key Vault is the intended source. The main integration defect is contractual: the ExternalSecret does not construct the `DATABASE_URL` consumed by Helm. `resolve_database_uri()` accepts any non-empty URI and falls back to repository-local SQLite when absent (`platform-portal/portal/database_config.py:23-35`); production should instead validate an allowed PostgreSQL scheme/host/TLS mode and fail closed, while retaining SQLite only under an explicit development/test configuration.

Connection URLs include credentials and must never appear in exception messages, SQLAlchemy engine logging, shell tracing, `kubectl describe`, Terraform textual plans, or artifacts. Key Vault rotation is not automated, and Kubernetes CSI rotation is disabled. The runtime should not use the server administrator account.

## 8. Infrastructure findings

Infrastructure strengths include private PostgreSQL, TLS enforcement, workload identity, non-root pods, seccomp, capability dropping, HTTPS ingress, and some deny/allow NetworkPolicies. Weaknesses are inconsistent ownership/application of those policies, a publicly routed private app, writable root filesystem, default service-account token behavior, mutable image references, and incomplete AKS control-plane hardening. The checked-in standalone `kubernetes/deployment.yaml:1-60` is also stale relative to the Helm workload (different namespace, image, port and no pod/container security context); stale deployable manifests create accidental insecure deployment paths and should be removed or clearly rendered/non-authoritative after migration.

## 9. CI/CD security findings

Useful controls are least-privilege baseline permissions, OIDC, tests, Helm rendering, Trivy image/repository scans, SBOM production, a blocking PostgreSQL Checkov job, immutable SHA image promotion, and environment-gated Terraform applies. Gaps are incorrect path filters, soft-failing general Checkov, mutable third-party action references, no explicit dependency-review/secret-scanning workflow in the repository, and promotion that pushes directly to `main` (`.github/workflows/app-deploy.yml:224-311`). The production environment's required reviewers and branch protection are external settings and could not be verified.

Terraform binary plans are uploaded for one day (`.github/workflows/terraform.yml:119-131,168-178`). Plans can contain sensitive values; access and retention should be minimized and the plan/apply identity separation reviewed. The dedicated PostgreSQL workflow appropriately avoids saving its textual plan, but it still prints a plan to logs, so redaction and access controls remain important.

## 10. Test-only route risks

`POST /__e2e__/athlete-session/<athlete_id>` clears the session and selects any existing athlete without authentication or CSRF (`e2e/support/run_server.py:31-43`). It is currently defined only by the E2E launcher, uses a placeholder-only key, binds to `127.0.0.1`, and uses a freshly deleted/recreated `.tmp` SQLite database. Those are meaningful controls.

The remaining risks are operational: `E2E_BASE_URL` disables the local server (`playwright.config.ts:24-31`), so the suite could target an operator-supplied environment; traces/screenshots may contain fixture or accidentally real data and are uploaded on failure (`browser-tests.yml:54-62`). The `authenticatedState` fixture is explicitly a no-op (`e2e/fixtures/test.ts:12-16`), so current coach E2E tests prove anonymous access, not authentication.

Guardrails should make the E2E route impossible to register outside an E2E-only entry point, require an unpredictable run token even on loopback, reject non-loopback hosts, and refuse non-allow-listed `E2E_BASE_URL` values in CI. Never ship `e2e/` in an application image. Add a production image test asserting the route is 404 and authentication tests using genuine test-tenant identities.

## 11. Threat scenarios

1. **Anonymous portal compromise:** an attacker visits the public production ingress, enumerates `/athletes/<id>`, reads health/nutrition notes, and modifies programmes because C-01/H-02 expose unguarded object routes.
2. **Cross-site coach action:** a logged-in coach visits an attacker page that submits a hidden form to archive/delete a block or review a check-in because H-03 provides no CSRF token.
3. **Tenant user becomes coach:** any identity accepted by the OAuth2 Proxy issuer and wildcard email policy accesses `/coach`; no Flask role check prevents it (H-01).
4. **Athlete impersonation:** a weak or leaked Flask signing key allows fabrication of `athlete_id`; alternatively a URL ID is changed on unscoped endpoints (H-02/H-04).
5. **Credential spill during cutover:** an operator manually composes missing `DATABASE_URL`, places it in an unmanaged Secret or CI command, and it reaches shell history, logs, events, or artifacts (H-06/M-08).
6. **Compromised pod expansion:** writable filesystem, mounted default service-account token, token-forwarding, and incomplete NetworkPolicies give a web compromise additional credentials and network reach (M-02 through M-04).
7. **CI supply-chain compromise:** a mutable action/image tag or dependency update executes in a job with OIDC/write permission, or missed path filters prevent scanning of a vulnerable portal change (M-07/L-01/L-02).
8. **E2E misuse:** an operator points Playwright at a shared environment; mutation tests create records and failure traces retain sensitive pages, while the no-op auth fixture gives false confidence.

## 12. Prioritised remediation plan

| Priority | Work | Findings | Exit test |
|---:|---|---|---|
| P0 | Remove the private app from public ingress; deploy only `public_app` publicly; require identity at app and ingress | C-01 | Anonymous/public-host route matrix cannot reach private data |
| P0 | Implement roles, Entra subject mapping, coach allow-list/assignment, and scoped object queries | H-01, H-02 | Two-user/two-coach negative authorisation suite passes |
| P0 | Add global CSRF and explicit public exemptions/abuse controls | H-03 | Every mutation rejects missing/cross-session tokens without state change |
| P0 | Establish production session/key/cookie policy and eliminate client-selected athlete authority | H-04 | Startup, cookie, tamper, rotation and revocation tests pass |
| P0 | Complete Key Vault-to-`DATABASE_URL` delivery and use least-privilege DB roles | H-06, M-08 | Clean-environment migration/app and rotation rehearsal pass without leakage |
| P1 | Add request schemas, size/rate limits, error handling and sensitive-log redaction | H-05, L-03 | Fuzz/boundary/413/429/log-scrub tests pass |
| P1 | Add headers and harden pod/network/AKS settings | M-01–M-05 | Header, manifest-policy, connectivity and Azure posture tests pass |
| P1 | Correct CI triggers and make IaC policy blocking | M-06, M-07 | Deliberately vulnerable fixtures fail before deploy/apply |
| P2 | Pin supply chain, lock/hash dependencies, remove stale manifests, formalise upload guardrails | L-01, L-02, L-04 | Policy and reproducible-build tests pass |
| P2 | Replace E2E auth placeholder and harden test-only launcher/artifacts | Test-only risks | Production route 404 plus real-role browser tests pass |

## 13. Release blockers

Release of private coaching/athlete functionality is blocked until all of the following are demonstrated in a release-like environment:

- C-01 is closed: public hosts cannot route to any private blueprint and direct service access fails closed.
- H-01 and H-02 are closed: authenticated identities, roles, coach assignments, and athlete ownership are enforced server-side for every route and nested object.
- H-03 is closed for all authenticated mutations.
- H-04 is closed: production identity/session configuration is explicit, secret-backed, tamper-resistant, revocable, and tested across replicas.
- H-06 is closed: Key Vault reliably supplies a TLS-enforcing, least-privilege database configuration without manual secret handling.
- H-05 must be closed before exposing anonymous high-volume forms or expensive programme generators to untrusted traffic.

If the release is strictly limited to the dedicated `public_app` lead/application surface, that narrower release still requires verified routing separation, CSRF-exemption rationale, rate limiting/bot protection, stronger validation, security headers, and confirmation that no private blueprint is present in its URL map.

## 14. Non-blocking follow-up work

- Complete the medium/low hardening items after the identity boundary is fixed, using risk owners and due dates.
- Add audit events for successful/failed login, role denial, coach access to athlete records, material mutations, exports, and administrative changes. Log stable actor/target IDs and outcome, never health notes, form bodies, cookies, tokens, or connection URLs.
- Define retention, deletion, subject-access, backup/restore, and breach-response procedures for athlete health data and coaching applications.
- Add automated secret scanning and history review; this audit inspected the current tree only and did not assert that repository history is clean.
- Document security contacts, vulnerability intake, dependency remediation SLAs, access reviews, Key Vault/state break-glass, and credential rotation rehearsals.
- Add backup restoration and tenant/athlete deletion tests; evaluate encryption requirements for SQLite PVCs and PostgreSQL backups.

## 15. Verification test catalogue

Each remediation above includes a specific verification. The release gate should additionally run this consolidated suite:

- **Route inventory test:** enumerate Flask `url_map`; require every endpoint to be explicitly public, coach, athlete, health, or test-only; fail on unclassified routes.
- **Authentication matrix:** anonymous, disabled, wrong-tenant, wrong-role, valid athlete, assigned coach, unassigned coach, and administrator against every route/method.
- **Object isolation matrix:** replace athlete, check-in, block, week, session, prescription, and exercise IDs across path/form/JSON; assert denial and unchanged database.
- **CSRF matrix:** missing, malformed, replayed, expired and wrong-session tokens on every POST/PATCH/PUT/DELETE; include cross-origin Playwright tests.
- **Cookie/session suite:** flags, scope, lifetime, fixation, tampering, logout, revocation, rotation and multi-replica continuity.
- **Input/abuse suite:** schema boundaries, Unicode, oversized bodies, malformed JSON, excessive nesting, record floods and rate limits; assert 4xx, rollback, and stable latency.
- **Header/error suite:** CSP/HSTS/clickjacking/MIME/referrer/cache headers and generic error bodies on every response class.
- **Secret suite:** clean namespace synchronization, missing-secret startup failure, rotation, least-privilege database operations, and automated scans of logs/artifacts for credential patterns without outputting matches.
- **Manifest policy suite:** non-root, read-only root, dropped capabilities, seccomp, no default token, resource limits, immutable image, probes, TLS and NetworkPolicies.
- **CI trigger fixture:** touch each application/dependency/IaC/container/workflow path and assert the appropriate scanners run and block an injected violation.
- **E2E boundary:** assert production image has no `/__e2e__/*` route, runner refuses production/shared URLs, test data uses reserved domains, and artifact access/retention is constrained.
- **Upload absence/policy:** fail the route inventory if multipart/file handling appears without the upload security test pack described in L-04.

## 16. Assumptions and limitations

- This was static review of the checked-out repository only. No live Azure, AKS, Key Vault, GitHub, DNS, ingress-controller, database, registry, or OAuth2 Proxy state was queried.
- Repository configuration may be stale, duplicated, proposed, or overridden externally. The report treats `.github/workflows/app-deploy.yml`, `flask-app/values-production.yaml`, and the referenced ingress/manifests as release-capable because the repository does not provide evidence that they are inert.
- GitHub environment protection, branch protection, CODEOWNERS enforcement, secret scanning settings, Dependabot, action allow-lists, artifact ACLs, Entra app/group configuration, workload-identity federation, Key Vault RBAC/firewall/purge protection, Kubernetes admission policy, and cloud audit settings cannot be confirmed from this tree.
- No dynamic DAST, dependency database refresh, container build, Helm/Kubernetes policy engine, Terraform plan, test execution, password cracking, or secret-value retrieval was performed. Scanner presence is confirmed; current scanner results are not.
- Current working-tree and Git history secret exposure were not exhaustively forensically scanned. Literal strings in unit tests are recognised placeholders and are not reported as real secrets.
- Jinja autoescaping was assumed for normal HTML templates; browser-side DOM sinks and every rendered value were not exhaustively data-flow analysed.
- No file upload feature was found. This conclusion is limited to repository-visible Python routes and does not cover external services.
- Severity reflects plausible confidentiality/integrity impact for athlete health and coaching data and the apparent production routing, not a live exploit demonstration.

