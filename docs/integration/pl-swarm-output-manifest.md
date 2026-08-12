# Powerlifting swarm output integration manifest

Generated from the 28 patch/summary pairs captured in `integration-inputs` at 2026-08-12 21:49:57 BST. The common source snapshot is `be85666afc6c889070bce25701c729445a976a68` on `integrate/v713-reconcile`.

## Integration rules and ordering

- Preserve the canonical British-English `Organisation` domain and fail closed when Organisation context or ownership is missing or ambiguous.
- Preserve the migration line `0019 -> 0020_organisation_ownership_domain -> 0021_saas_billing_foundation -> 0022_support_admin_foundation`. The PDF meal-plan migration supplied as another `0021` must be renumbered after `0022` when ported; do not merge either competing filename unchanged.
- Integrate tenancy primitives before tenant-scoped routes, then invitations/onboarding, migration verification, release gates, product features, and finally assurance/documentation.
- `KEEP` means the preferred source for its task, subject to ordinary review and rebasing. `SELECTIVE` means port only the described portions after reconciling hotspots. `SKIP` means retain as historical/reference evidence and do not merge product changes.
- Source-reported commit failures caused only by read-only `.git` are not product blockers. Runtime dependency gaps, stalled Playwright, skipped PostgreSQL tests, and reported broader-suite failures remain evidence limitations.

## Recommended sequence

1. `saas-01`, then selectively reconcile `saas-02` through `saas-05`.
2. Use `saas-07` as the canonical migration/verifier source; selectively add onboarding from `saas-06` and deployment/E2E gates from `saas-08` without their duplicate migrations.
3. Port the canonical product-hardening sources listed below, always rebasing authentication, athlete lookup, meal-plan, and performance changes onto the completed Organisation scope.
4. Add assurance packages and documentation, updating any stale expected migration head to `0022_support_admin_foundation`.

## SaaS integration sources

### `saas-01-tenancy-context-core` — KEEP — priority P0

- **Changed files:** `platform-portal/portal/tenancy.py`; `platform-portal/tests/test_tenancy.py`.
- **Major behavior:** immutable request/service tenancy context, active membership resolution, explicit selection for multi-Organisation coaches, Organisation-role decorators, and fail-closed tenant/athlete loaders.
- **Test evidence:** 10 tests passed; `git diff --check` passed; no conflict markers.
- **Hotspots:** foundational dependency for all scoped route work; reconcile later helper variants (`organisation_access.py`, `organisation_scope.py`, and `tenancy_verifier.py`) into this single vocabulary/API.
- **Recommendation:** merge as the canonical tenancy-context foundation. Do not create a second tenant model or parallel context mechanism.

### `saas-02-athlete-programming-isolation` — SELECTIVE — priority P0

- **Changed files:** `portal/athletes.py`; `portal/programming_routes/{athletes,blocks,sessions,weeks}.py`; `portal/services/organisation_access.py`; `tests/test_cross_tenant_security.py` (all under `platform-portal`).
- **Major behavior:** Organisation-scoped athlete list/profile/onboarding and direct-ID programming reads/mutations, with athlete self-scope preserved and cross-tenant probes promoted from expected failures.
- **Test evidence:** compileall and `git diff --check` passed; runtime pytest unavailable because Flask was missing.
- **Hotspots:** `athletes.py` and `test_cross_tenant_security.py` overlap `saas-08`; the access helper overlaps `saas-01`, `saas-03`, and `saas-04`.
- **Recommendation:** selectively port route enforcement and regression tests onto the `saas-01` API; consolidate helpers rather than keeping parallel scope implementations.

### `saas-03-checkins-nutrition-isolation` — SELECTIVE — priority P0

- **Changed files:** `portal/checkins.py`; `portal/nutrition_imports.py`; `portal/nutrition_prescriptions.py`; `portal/services/organisation_scope.py`; `tests/test_cross_tenant_security.py`; `tests/test_nutrition_import.py`; `tests/test_nutrition_macro_delivery.py`.
- **Major behavior:** fail-closed Organisation scoping for check-in list/read/review and nutrition history/create/import/update paths.
- **Test evidence:** 76 focused/authorization tests passed; compile and `git diff --check` passed; relevant strict-xfail markers removed.
- **Hotspots:** shared cross-tenant test fixture and duplicate `organisation_scope.py` implementation with `saas-04`.
- **Recommendation:** port behavior and tests, folding the scope helper into the canonical tenancy service.

### `saas-04-mealplan-performance-isolation` — SELECTIVE — priority P0

- **Changed files:** `portal/__init__.py`; `portal/api/athlete_performance.py`; `portal/meal_plan_delivery.py`; `portal/repositories/meal_plans.py`; `portal/services/meal_plan_files.py`; `portal/services/organisation_scope.py`; `tests/test_cross_tenant_security.py`; `tests/test_performance_chart_api.py`.
- **Major behavior:** Organisation isolation for meal plans/files and performance athlete IDs.
- **Test evidence:** focused suite 18 passed/11 unrelated xfailed; full suite 706 passed, 2 skipped, 11 xfailed, and 6 pre-existing migration/schema reconciliation failures; `git diff --check` passed.
- **Hotspots:** direct overlap with product performance and PDF meal-plan sources, plus `saas-08`; duplicate scope helper with `saas-03`.
- **Recommendation:** port tenant guards and negative tests first, then rebase product feature implementations around them. Keep only one file-storage service.

### `saas-05-canonical-invitations` — SELECTIVE — priority P1

- **Changed files:** `migrations/versions/0020_organisation_ownership_domain.py`; `portal/models/__init__.py`; `portal/models/organisation.py`; `portal/services/organisation_invitations.py`; `tests/test_organisation_domain.py`.
- **Major behavior:** hashed invitation tokens, durable delivery state, expiry/email/issuer validation, atomic one-time acceptance, membership creation, revocation, and supersession using only canonical Organisation models.
- **Test evidence:** 18 focused tests and Ruff passed; `git diff --check` passed; broader migration tests had stale/forward-schema expectations.
- **Hotspots:** modifies canonical `0020`, Organisation models, and exports; invitation use overlaps onboarding.
- **Recommendation:** port the invitation domain/service/tests, but review any edit to `0020` against the reconciled migration already present. Never add another invitation or tenant model.

### `saas-06-pl-onboarding-entitlements` — SELECTIVE — priority P1

- **Changed files:** `portal/__init__.py`; `portal/organisation_onboarding.py`; `portal/services/organisation_onboarding.py`; `templates/organisation/**`; `tests/test_organisation_onboarding.py`; `migrations/versions/0021_saas_billing_foundation.py`.
- **Major behavior:** atomic Organisation/owner onboarding, optional canonical invitations, athlete ownership assignment, starter/team/unlimited plans, and fail-closed subscription/capability/limit checks.
- **Test evidence:** Python compilation, `git diff --check`, and conflict scan passed; pytest unavailable because Flask/SQLAlchemy were missing.
- **Hotspots:** `portal/__init__.py`, invitation and ownership services, and a duplicate `0021` also supplied by `saas-07`/`saas-08`.
- **Recommendation:** port onboarding/UI/entitlement behavior after tenancy and invitations. Use the reviewed `saas-07` migration chain as canonical and reconcile model assumptions; do not copy a second `0021`.

### `saas-07-migration-verifier-tests` — KEEP — priority P0

- **Changed files:** `migrations/versions/0021_saas_billing_foundation.py`; `migrations/versions/0022_support_admin_foundation.py`; `tests/test_database_migrations.py`; `tests/test_v713_tenant_model_audit.py`; `scripts/migrations/saas_tenancy_verify.py`; `scripts/migrations/tests/test_saas_tenancy_verify.py`.
- **Major behavior:** canonical billing/support migration continuation and read-only verifier updated to `Organisation`, expected head `0022_support_admin_foundation`, removed-schema detection, ownership completeness, tenant-edge integrity, constraints, nullability, and indexes.
- **Test evidence:** 18 focused migration/schema tests passed with 1 PostgreSQL test skipped; 28 adjacent SaaS tests passed with 14 existing xfails; `git diff --check` and conflict scan passed.
- **Hotspots:** migrations/verifier/tests overlap `saas-06` and heavily overlap `saas-08`.
- **Recommendation:** use as the canonical source for `0021`, `0022`, migration audits, and the comprehensive verifier. Execute the PostgreSQL-backed test before release.

### `saas-08-release-e2e-gates` — SELECTIVE — priority P1

- **Changed files:** `.github/workflows/app-deploy.yml`; `e2e/support/{run_server,seed_database}.py`; `e2e/tests/saas-tenancy.future.spec.ts`; Helm values and migration job; `portal/{__init__,athletes,auth,database_cli,meal_plan_delivery}.py`; `portal/tenancy_verifier.py`; cross-tenant/migration audit tests; GitOps promotion scripts/tests; migration verifier/tests; release evidence/tests; duplicate `0021`/`0022` migrations.
- **Major behavior:** exact-head deployment gates, pre/post-deploy tenancy verification, digest promotion evidence, and two-Organisation negative E2E probes across athlete/programming/check-in/nutrition/meal-plan paths.
- **Test evidence:** 15 release/migration/promotion tests and 39 focused tenancy/domain tests passed; Helm lint/render passed; one unrelated xfail; full collection lacked PyYAML and Playwright stalled.
- **Hotspots:** widest overlap in the swarm: migrations, verifier, auth, athlete and meal-plan routes, cross-tenant fixtures, release evidence, E2E seed, and deployment workflow.
- **Recommendation:** selectively port deployment, immutable-image, exact-head, and E2E gate changes. Take migrations and the general verifier from `saas-07`; take route scoping from `saas-02`–`04`; do not blindly apply this whole patch.

## Duplicate product-hardening runs

The `product1-*` and `product2-*` sets repeat the same eight task briefs but contain materially different implementations. The canonical choices are: meet day `product2-01`; performance intelligence `product1-02`; PDF meal plans `product1-03`; coach UX `product1-04`; observability `product1-05`; athlete API `product1-06`; beta readiness `product1-07`; regression matrix `product2-08`.

### Meet prep/game day

#### `product2-01-meet-prep-game-day` — KEEP — priority P2 (canonical)

- **Changed files:** `portal/meet_day.py`; `portal/services/meet_day.py`; `static/css/meet_day.css`; `templates/meet_day/detail.html`; `tests/test_meet_day.py`.
- **Major behavior:** countdown/readiness summary, federation/weight/bodyweight gaps, nine-attempt completeness and result counts, handler notes, attempt-change cues, and safe incomplete states.
- **Test evidence:** compileall, `git diff --check`, and conflict scan passed; focused pytest dependencies unavailable. A source commit was recorded (`5e6ebde...`).
- **Hotspots:** exact five-file overlap with `product1-01`.
- **Recommendation:** canonical source because its readiness accounting is more explicit; re-run focused Flask tests after port.

#### `product1-01-meet-prep-game-day` — SKIP — priority reference only

- **Changed files:** same five meet-day files as `product2-01`.
- **Major behavior:** similar countdown, federation/bodyweight, handler-note, per-athlete readiness, and empty-state work.
- **Test evidence:** compilation and `git diff --check` passed; pytest could not collect.
- **Hotspots:** wholly duplicates the canonical meet-day task.
- **Recommendation:** retain as comparison/test inspiration only; do not merge alongside `product2-01`.

### Performance intelligence

#### `product1-02-performance-intelligence-hardening` — KEEP — priority P2 (canonical)

- **Changed files:** `portal/api/athlete_performance.py`; `portal/services/{coach_athlete_performance,performance_charts,performance_decisions}.py`; `tests/test_performance_chart_api.py`; `tests/test_performance_decisions.py`.
- **Major behavior:** excludes partial sessions, validates evidence ranges, adds S/B/D block comparisons and completed-meet trends, exposes data quality, bounds windows, and stabilizes explanations.
- **Test evidence:** compileall and `git diff --check` passed; runtime dependencies unavailable.
- **Hotspots:** tenant guard in `saas-04`; performance services/tests in `product2-02`; query audit in `assurance-02`.
- **Recommendation:** canonical for broader PL-specific analytical behavior, but apply only after `saas-04` and preserve its fail-closed athlete loader.

#### `product2-02-performance-intelligence-hardening` — SELECTIVE — priority P2

- **Changed files:** `portal/api/athlete_performance.py`; `portal/services/{athlete_performance,performance,performance_charts,performance_decisions}.py`; three performance test files.
- **Major behavior:** incomplete-set reporting, invalid evidence exclusion, partial-data metadata, conservative decisions, and bounded/min-date-safe queries.
- **Test evidence:** edited code compiled and `git diff --check` passed; focused tests could not collect. A source commit was recorded (`7048222...`).
- **Hotspots:** overlaps canonical source and `saas-04`.
- **Recommendation:** selectively port unique minimum-date boundary and lower-level service tests if absent after canonical integration; otherwise skip its product implementation.

### PDF meal-plan delivery

#### `product1-03-meal-plan-pdf-delivery` — SELECTIVE — priority P2 (canonical implementation)

- **Changed files:** E2E seed/spec; `portal/{__init__,auth,meal_plan_delivery}.py`; meal-plan model/exports; athlete/coach templates; `tests/test_pdf_meal_plan_delivery.py`; `migrations/versions/0021_pdf_meal_plan_delivery.py`.
- **Major behavior:** validated PDF upload, draft/publish, effective metadata, immutable checksummed revisions, athlete current/history/download, and preserved provider authoring.
- **Test evidence:** 11 focused tests passed; clean SQLite migration verified; Playwright discovery, compileall, and `git diff --check` passed; broader migration suite had 5 concurrent-schema failures.
- **Hotspots:** its `0021` conflicts with canonical billing `0021`; auth/init/meal-plan/E2E seed overlap SaaS scope and release gates.
- **Recommendation:** canonical feature source, but selectively port it after tenancy. Renumber/rebase its migration after canonical `0022`, and retain `saas-04` access checks.

#### `product2-03-meal-plan-pdf-delivery` — SKIP — priority reference only

- **Changed files:** same integration surfaces plus separate `pdf_meal_plan.py`, `pdf_meal_plans.py`, two PDF-specific templates, and the competing `0021_pdf_meal_plan_delivery.py`.
- **Major behavior:** broadly duplicates upload/publish/revision/history/download behavior.
- **Test evidence:** compilation, `git diff --check`, and conflict scan passed; pytest and Playwright dependencies unavailable.
- **Hotspots:** duplicates canonical PDF feature and introduces a parallel model/service shape.
- **Recommendation:** documentation/reference only; do not merge a second meal-plan model or competing migration.

### Coach UX

#### `product1-04-coach-ux-qa` — KEEP — priority P3 (canonical)

- **Changed files:** coach E2E spec; `static/css/coach_workspace.css`; athlete list and coach base/dashboard templates; `tests/test_coach_workspace.py`.
- **Major behavior:** denser flat workspace/roster/forms/tables, responsive cleanup, skip-link focus, and accessible email errors while preserving routes/test IDs.
- **Test evidence:** 10 focused tests and `git diff --check` passed; full Flask/E2E dependencies unavailable.
- **Hotspots:** dashboard/CSS/E2E overlap `product2-04`.
- **Recommendation:** merge as canonical because of stronger executed focused coverage and explicit accessibility work.

#### `product2-04-coach-ux-qa` — SELECTIVE — priority P3

- **Changed files:** coach E2E spec; applications/workspace CSS; workspace JS; application detail/index and dashboard templates; `tests/test_coach_ux_hardening.py`.
- **Major behavior:** similar visual hardening plus Escape-to-close mobile navigation/focus restoration and application-surface changes.
- **Test evidence:** 4 focused tests, JavaScript syntax, and `git diff --check` passed; Flask/Playwright unavailable.
- **Hotspots:** dashboard/workspace/E2E overlap canonical source; unique application and JS surfaces.
- **Recommendation:** port only the mobile navigation accessibility behavior and non-conflicting application-page improvements after visual review.

### Observability/release evidence

#### `product1-05-observability-release-evidence` — KEEP — priority P2 (canonical)

- **Changed files:** platform-status collector; engineering overview and release-readiness services; `static/app.js`; GitOps/release-readiness templates; three focused test files.
- **Major behavior:** image, Argo, DB-head, and freshness reporting; preserves stale evidence while readiness fails closed; current/stale/unavailable coverage.
- **Test evidence:** Python/JavaScript syntax and `git diff --check` passed; pytest lacked Flask.
- **Hotspots:** collector/overview/app/GitOps overlap `product2-05`; release semantics intersect `saas-08`.
- **Recommendation:** canonical because it explicitly fails readiness closed while retaining stale diagnostic evidence. Reconcile expected head with `0022`.

#### `product2-05-observability-release-evidence` — SELECTIVE — priority P2

- **Changed files:** collector; engineering overview/executive dashboard services, CSS, template, GitOps template, app JS, and focused tests.
- **Major behavior:** similar image/Argo/head/freshness reporting plus Argo-revision fallback and executive-dashboard presentation.
- **Test evidence:** py_compile, isolated collector contract, `git diff --check`, and conflict scan passed; full pytest unavailable.
- **Hotspots:** shared collector/UI files with canonical source.
- **Recommendation:** selectively port unique Argo-revision fallback and executive-dashboard tests/UI after canonical collector integration.

### Athlete application contract

#### `product1-06-athlete-app-contract` — KEEP — priority P2 (canonical)

- **Changed files:** `portal/__init__.py`; `portal/auth.py`; `portal/api/athlete_app.py`; `portal/services/athlete_app_contract.py`; `tests/test_athlete_app_contract.py`.
- **Major behavior:** integrated athlete-only `/api/athlete/v1` endpoints for today, programmes, logging, check-ins, nutrition/PDF capability, and progress, with identity-derived self-scope and coach rejection.
- **Test evidence:** 92 focused/regression tests passed; py_compile and `git diff --check` passed.
- **Hotspots:** auth/init overlap SaaS gates and PDF delivery; contract must use final Organisation-safe authentication.
- **Recommendation:** canonical due to integrated implementation and strongest runtime evidence; port after auth/tenancy reconciliation.

#### `product2-06-athlete-app-contract` — SKIP — priority reference only

- **Changed files:** `docs/v7.13-athlete-app-api-contract.md`; `portal/athlete_app_contract/**`; `tests/test_athlete_app_contract.py`.
- **Major behavior:** versioned DTO/service/route contract with integration deliberately deferred to avoid auth conflicts.
- **Test evidence:** compileall and `git diff --check` passed; pytest lacked Flask. A source commit was recorded (`9a8b79e...`).
- **Hotspots:** duplicates the integrated canonical API but packages a parallel implementation tree.
- **Recommendation:** retain the contract document as reference only; do not merge the parallel code package.

### Beta readiness documentation

#### `product1-07-beta-readiness-runbook` — KEEP — priority P4 (canonical)

- **Changed files:** `docs/README.md`; `docs/beta-readiness/**` (including smoke checklist and support/incident runbook).
- **Major behavior:** onboarding, acceptance, support, incident/forward repair, recovery evidence, boundaries, limitations, and an explicit shared multi-coach NO-GO until tenant isolation/restore evidence exists.
- **Test evidence:** documentation/reference/whitespace checks and `git diff --check` passed.
- **Hotspots:** docs index and content overlap `product2-07`, assurance backup/security, and release matrix.
- **Recommendation:** canonical because its structured package is easier to operate and preserves a clear fail-closed readiness decision; refresh claims after code integration.

#### `product2-07-beta-readiness-runbook` — SKIP — priority reference only

- **Changed files:** `docs/README.md`; `docs/v7.13-multi-coach-beta-readiness.md`.
- **Major behavior:** single-document version of the same readiness, support, incident, backup, limitations, and smoke requirements.
- **Test evidence:** documentation structure/reference checks and `git diff --check` passed.
- **Hotspots:** duplicates canonical beta-readiness documentation.
- **Recommendation:** documentation reference only; use it to cross-check omissions, not as a second authoritative runbook.

### PL regression matrix

#### `product2-08-pl-regression-matrix` — KEEP — priority P3 (canonical)

- **Changed files:** `docs/release/README.md`; `docs/release/release-checklist.md`; `docs/release/pl-regression-matrix.md`; `scripts/release/tests/test_pl_regression_matrix.py`.
- **Major behavior:** authoritative ten-lane PL matrix, ordered Playwright smoke, 50+ test references, release-gate expectations, and exclusion of the future tenancy fixture from current evidence.
- **Test evidence:** 11 tests plus 10 subtests passed; `git diff --check` passed; Playwright unavailable.
- **Hotspots:** release docs/checklist and conceptual overlap with `product1-08` and `saas-08`.
- **Recommendation:** canonical because it is wired into existing release documentation and has stronger drift-test coverage.

#### `product1-08-pl-regression-matrix` — SKIP — priority reference only

- **Changed files:** `docs/testing/pl-regression-matrix.md`; `tests/test_pl_regression_matrix.py`.
- **Major behavior:** alternate matrix/smoke ordering with residual PostgreSQL, browser, entitlement, and tenancy boundaries.
- **Test evidence:** 3 matrix and 7 release-helper tests passed; compile/whitespace/conflict checks passed; representative portal suites lacked dependencies.
- **Hotspots:** duplicates the canonical matrix in a different documentation/test location.
- **Recommendation:** documentation reference only; port any missing boundary wording into `product2-08` rather than keeping two authorities.

## Assurance sources

### `assurance-01-backup-dr-restore` — SELECTIVE — priority P1

- **Changed files:** `docs/README.md`; `docs/backup-dr-restore-assurance.md`; `scripts/backup_dr/**` including `restore_verify.py` and its tests.
- **Major behavior:** RPO/RTO and gap inventory, non-destructive restore rehearsal, sanitized evidence, read-only schema/table/constraint checks, object-store/PDF recovery gate, and rollback/forward-repair/PITR decisions.
- **Test evidence:** 5 isolated tests, Python compilation, CLI rejection, offline one-head graph, and `git diff --check` passed; no external system was touched.
- **Hotspots:** verifier recorded the then-current `0020` head and must be updated to canonical `0022`; docs overlap beta-readiness and case study.
- **Recommendation:** port the assurance package and tests after correcting expected-head/examples and reviewing critical tables against the final schema.

### `assurance-02-load-performance-engineering` — KEEP — priority P3

- **Changed files:** `performance/**` (k6 profiles, documentation, tests); `platform-portal/tests/test_performance_query_audit.py`.
- **Major behavior:** localhost-safe/read-write-opt-in PL load profiles for coach, athlete sessions, block preview, check-ins, nutrition, performance charts, and meal plans; latency/resource thresholds and constant-query regressions.
- **Test evidence:** 9 focused tests, JavaScript syntax, and `git diff --check` passed.
- **Hotspots:** query audit intersects canonical performance intelligence; meal-plan path documentation predates PDF route integration.
- **Recommendation:** merge, then update the PDF route and exercise profiles against a disposable environment only.

### `assurance-03-security-threat-model` — KEEP — priority P1

- **Changed files:** `docs/security/pl-saas-threat-model.md`; `platform-portal/tests/test_security_assurance.py`.
- **Major behavior:** 12 STRIDE-classified threats, six release blockers, fail-closed auth/cookie/redirect assertions, and a guard against treating tenant-gap xfails as acceptance.
- **Test evidence:** syntax, threat-register counts, tenant-gap retention, diff, and conflict checks passed; pytest collection lacked Flask.
- **Hotspots:** release conclusion must be reassessed only after all SaaS isolation tests pass; security test reads cross-tenant contracts.
- **Recommendation:** merge as assurance documentation/tests. Preserve its NO-GO conclusion until evidence genuinely closes the blockers.

### `assurance-04-portfolio-case-study` — KEEP — priority P4 (documentation only)

- **Changed files:** `docs/README.md`; `docs/platform-engineering-case-study.md`.
- **Major behavior:** recruiter/client-facing, repository-evidenced narrative separating implemented, historical, proposed, and incomplete platform capabilities.
- **Test evidence:** 10 focused migration/release tests passed; links, whitespace, conflict scan, and `git diff --check` passed; broader app collection lacked Flask/SQLAlchemy.
- **Hotspots:** documentation index and claims overlap all assurance/readiness material and can become stale after integration.
- **Recommendation:** retain/merge as documentation only after a final fact and test-count refresh; it is not product or release evidence.

## Cross-source hotspot index

- **`portal/__init__.py` and `portal/auth.py`:** SaaS release gates, PDF meal plans, and athlete API. Resolve tenancy/auth first; deny missing or ambiguous Organisation context.
- **`portal/athletes.py` and `tests/test_cross_tenant_security.py`:** route isolation sources and release E2E gates. Preserve all negative direct-ID cases while deduplicating fixtures.
- **Meal-plan model/delivery/files:** `saas-04`, both PDF runs, and `saas-08`. Use canonical existing meal-plan models, one storage service, tenant-qualified lookup, and a post-`0022` feature migration.
- **Performance API/services/tests:** `saas-04`, both performance runs, and `assurance-02`. Tenant qualification is a prerequisite to analytics behavior.
- **Migrations/verifiers:** `saas-06`, `saas-07`, `saas-08`, PDF sources, and backup assurance. Canonicalize on `0021_saas_billing_foundation` and `0022_support_admin_foundation`; no second `0021`.
- **E2E seed:** PDF delivery and `saas-08`. Create two Organisations and ensure every seeded ownership/membership is explicit.
- **Release/readiness evidence:** `saas-08`, both observability runs, both regression matrices, and beta/assurance docs. Runtime gates are authoritative; narrative documents must not overstate readiness.

## Evidence limitations to close before release

- Run the complete portal suite after resolving the six reported migration/schema failures.
- Run PostgreSQL-backed migration and tenancy-verifier tests against a disposable database.
- Run ordered Playwright smoke and two-Organisation negative probes in a disposable environment; source reports include missing dependencies and one stalled runner.
- Re-run PDF persistence/migration tests after renumbering its migration beyond `0022`.
- Re-run focused meet-day, performance, observability, security, onboarding, and coach UX tests in the repository-supported Python environment.
