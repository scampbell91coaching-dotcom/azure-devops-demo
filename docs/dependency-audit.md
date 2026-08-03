# Dependency and supply-chain audit

Audit date: 2026-08-03  
Scope: repository evidence only; no dependency, lockfile, deployment, or remote-state changes were made.

## Executive summary

The npm dependency graph is small, development-only, and integrity-locked. Most direct Python packages are exactly pinned, but `azure-monitor-opentelemetry` and `prometheus-client` float, Python has no transitive lock or hashes, and the portal mixes `pytest` into its production requirements. Both Terraform roots have provider locks with checksums. The Helm charts have no chart dependencies.

The principal supply-chain risk is mutable references: every GitHub Action uses a tag rather than a commit SHA, all three Python base images use tags rather than digests, two third-party workload images use mutable tags, and Argo CD tracks `main`. The locally cached vulnerability scan found no HIGH/CRITICAL Python or npm package vulnerability, but its database was two days old and the npm result was offline; these results must not be read as a current advisory-service attestation.

Release status: **blocked for a security-sensitive release pending triage of the local Trivy CRITICAL AKS finding and confirmation with fresh CI vulnerability scans**. For a documentation-only release there is no dependency blocker.

## 1. Inventory of dependency sources

| Ecosystem | Source files | Purpose and resolution |
|---|---|---|
| Python, demo app | `app/requirements.txt`, `app/requirements-dev.txt` | Flask/Gunicorn runtime plus telemetry; pytest is separated into the dev file. Pip requirements have no hash lock. |
| Python, portal | `platform-portal/requirements.txt` | Flask/Gunicorn, ORM/migrations and PostgreSQL runtime; also includes pytest. No separate dev file or hash lock. |
| npm | `package.json`, `package-lock.json` | Playwright test tooling only. npm lockfile v3 contains four installed package entries, exact versions, registry URLs, and integrity hashes. |
| Playwright | `playwright.config.ts`, `e2e/**` | Chromium desktop and Pixel 7 emulation; CI installs the Playwright-matched Chromium build. |
| Containers | `Dockerfile`, `platform-portal/Dockerfile`, `platform-portal/Dockerfile.public` | Python base images and pip-installed application layers. Kubernetes/Helm manifests also reference application, Redis, and oauth2-proxy images. |
| GitHub Actions | `.github/workflows/*.yml` | 49 action uses across seven workflows, all referenced by version tags. Tool versions also appear in workflow setup/install commands. |
| Azure Pipelines | `azure-pipelines.yml` | Helm is set to `latest`; Trivy is installed from its apt repository without a package version. Included because these are additional supply-chain entry points. |
| Terraform | `infra/**/*.tf`, `infra/.terraform.lock.hcl`, `infra/aks/.terraform.lock.hcl` | Two roots constrain and checksum `hashicorp/azurerm`; the PostgreSQL child module also declares `hashicorp/random`, but the root lock does not contain it because the child module is consumed by the root. All modules are local. |
| Helm | `flask-app/Chart.yaml`, `lead-magnets-chart/Chart.yaml`, chart values/templates | Application chart versions `0.3.0` and `0.1.0`, both with `appVersion: 1.0.0`; neither declares chart dependencies or has `Chart.lock`. |
| Kubernetes/GitOps | `kubernetes/**`, `private-platform-manifests/**`, `argocd-applications/**`, `letsencrypt-prod.yaml` | Native resources, operator CRDs, image references, and Argo CD application sources. |
| Scanning | `platform-security.yml`, `app-deploy.yml`, `terraform.yml`, `postgresql-plan.yml`, `codeql.yml`, `azure-pipelines.yml` | Trivy, Checkov, CodeQL and SBOM generation. There is no repository configuration for Dependabot/Renovate, pip-audit, or a dedicated `npm audit` workflow. |

## 2. Pinned and unpinned dependencies

### Exactly or effectively pinned

- Demo Python runtime: `blinker 1.9.0`, `click 8.4.2`, `Flask 3.1.3`, `gunicorn 23.0.0`, `itsdangerous 2.2.0`, `Jinja2 3.1.6`, `MarkupSafe 3.0.3`, and `Werkzeug 3.1.8`; dev `pytest 8.4.1`.
- Portal direct requirements: `Flask 3.1.1`, `gunicorn 23.0.0`, `pytest 8.4.1`, `Flask-SQLAlchemy 3.1.1`, `SQLAlchemy 2.0.43`, `Flask-Migrate 4.1.0`, and `psycopg[binary] 3.2.9`.
- `package-lock.json`: `@playwright/test`, `playwright`, and `playwright-core` at `1.62.1`, with optional `fsevents 2.3.2`; all entries have integrity data. `npm ci` therefore resolves the locked graph despite the `^1.62.1` range in `package.json`.
- Terraform locks select `hashicorp/azurerm 4.81.0` with platform hashes in both roots. Production application image tags are full Git commit SHAs in `flask-app/values-production.yaml`, `lead-magnets-chart/values.yaml`, and `kubernetes/deployment.yaml`.
- Workflow tool inputs pin Python `3.12`, Node `20`, Terraform `1.15.8`, Helm `v3.17.3` in one workflow, and Checkov `3.3.8` in the PostgreSQL workflow.

### Floating or mutable

- `azure-monitor-opentelemetry` and `prometheus-client` have no constraints. All transitive Python dependencies float because there is no fully resolved lock or `--require-hashes` file.
- `package.json` allows compatible Playwright updates with `^1.62.1`; this matters when the lockfile is intentionally regenerated, not during `npm ci`.
- Terraform constraints `~> 4.0` for AzureRM and `~> 3.6` for Random permit minor releases when locks are refreshed. Terraform itself permits any `>= 1.15.0, < 2.0.0` outside the workflows.
- Docker bases `python:3.12-slim` and `python:3.14-slim` are not digest-pinned. `redis:7-alpine`, `quay.io/oauth2-proxy/oauth2-proxy:v7.9.0`, Helm's default `latest`, and the Azure Pipeline's published `latest` image are mutable references. A timestamp-like private image tag is immutable only by registry policy, which is not visible here.
- All Actions use mutable tags: `actions/checkout@v4` (15 uses), `setup-python@v5` (4), `setup-node@v4` (1), artifact actions (6), `azure/login@v2`/`@v3` (8), `setup-helm@v4` (2), `setup-terraform@v3` (7), CodeQL `@v3` (3), `docker/login-action@v4` (1), `aquasecurity/trivy-action@v0.36.0` (2), and `anchore/sbom-action@v0` (1).
- Both Argo CD applications use `targetRevision: main`. This is intentional continuous delivery but is not a reproducible source revision by itself.
- Azure Pipelines requests Helm `latest` and installs the current apt-distributed Trivy package.

## 3. Known audit findings visible from repository tools

Results below were produced locally on 2026-08-03 without refreshing remote data:

- Trivy `0.71.2`, using vulnerability DB timestamp 2026-08-01 12:50 UTC, found **0 HIGH/CRITICAL vulnerabilities** in both runtime Python requirement files. Dev dependencies were suppressed by default. It could not refresh its checks bundle and fell back to embedded checks.
- Trivy reported one **CRITICAL** misconfiguration: AKS API access is not restricted to specific IP ranges (`AZU-0041`, `infra/aks/main.tf`). It also reported five HIGH Kubernetes/Helm findings: writable root filesystem in the Flask chart, missing/default security contexts in the standalone Flask deployment, and a default pod security context for oauth2-proxy.
- Checkov `3.3.8 --skip-download` reported **16 passed, 22 failed, 7 skipped** Terraform checks. Findings include ACR public access/scanning/retention/trust controls, AKS API exposure/private-cluster/local-admin/logging/upgrade-channel and encryption controls, and a database subnet without an NSG. The general Terraform workflow runs Checkov with `--soft-fail`, so these do not gate it; the PostgreSQL-specific workflow is gating but scans only that module.
- Both Helm charts linted and rendered successfully. Terraform formatting passed. Offline Terraform validation could not run because local modules/providers had not been initialized/cached; this is an audit limitation, not a configuration failure.
- No committed scanner output, SARIF, SBOM, GitHub run result, or vulnerability exception file was found. CI generates Trivy SARIF and a 14-day SBOM artifact, so historical evidence is external to the repository.

## 4. npm audit findings and runtime impact

`npm audit --offline --json` reported 0 vulnerabilities across the lockfile graph. This used only locally cached advisory data and did not contact the npm registry, so it is **not evidence that the current npm advisory service has no findings**. `npm ls` could not validate the installed tree because `node_modules` is absent; that is expected in a clean checkout and `npm ci` is the correct verification step.

All npm packages are under `devDependencies` and are used only for Playwright browser tests. There are no npm runtime dependencies and no Node assets are copied into the Python production images. Consequently, any future npm audit finding in the present graph affects CI/developer test tooling, not the deployed application runtime, although a compromised test tool could still affect CI secrets, artifacts, or confidence in releases.

## 5. Python upgrade risks

- The portal container and CI run Python 3.12, but `Dockerfile.public` runs Python 3.14 with the same requirements. This creates an untested interpreter split: browser and portal tests do not prove Python 3.14 compatibility, especially for binary `psycopg[binary]` wheels and database/migration behavior.
- The portal pins Flask `3.1.1` while the demo pins `3.1.3`; maintaining two patch baselines increases testing and advisory-triage work.
- The demo directly pins several Flask transitive packages. This improves immediate determinism but can create resolver conflicts when Flask is upgraded unless the whole compatible set is tested together.
- The two floating telemetry packages can change direct and transitive dependencies on every clean build. OpenTelemetry distributions commonly have broad dependency surfaces; the exact graph is not recorded here.
- Python requirements contain neither artifact hashes nor a transitive lock, so exact direct versions do not guarantee byte-for-byte or transitive reproducibility.
- `pytest` is installed in portal production containers despite being used only by tests. Removing it from runtime requires splitting requirements and proving CI/Docker install the correct set.
- `psycopg[binary]` intentionally bundles native components. It eases deployment but expands binary provenance and platform-compatibility considerations compared with a system-linked build.

## 6. Docker-image risks

All three Dockerfiles run as non-root, use exec-form commands, and avoid pip's download cache. However, base tags are not digest-pinned, so identical source can inherit a different OS/Python layer later. `slim` and `alpine` tags also move as their distributions publish packages. The Dockerfiles do not create an image SBOM or provenance attestation themselves.

The GitHub application workflow gates HIGH/CRITICAL fixable Trivy image findings (`ignore-unfixed: true`, exit code 1). The Azure Pipeline generates a HIGH/CRITICAL report but blocks only fixable CRITICAL findings, leaving HIGH findings non-gating. Ignoring unfixed findings is operationally understandable, but it needs a documented exception/expiry process because exploitable unfixed issues otherwise disappear from the gate.

Application deployments use commit-SHA tags, which is stronger than `latest`, but tags are still replaceable unless ACR immutability is enforced. Third-party images and all Python bases should be recorded by digest. Trivy's repository filesystem scan does not substitute for scanning every final image; the public image workflow currently has no visible image-scan step.

## 7. GitHub Actions pinning risks

No Action is pinned to a full commit SHA. Major and minor tags can be moved by their publishers, so a previously reviewed workflow may execute different code. `anchore/sbom-action@v0` is especially broad, while `trivy-action@v0.36.0` narrows the release but remains a mutable tag. First-party Actions reduce but do not remove this risk.

Pin each `uses:` reference to a reviewed 40-character commit SHA and retain a trailing release comment for maintainability. Automate digest/SHA update pull requests and review release notes and permission changes. Keep the existing job-level permissions, but also split jobs where write or OIDC permissions are unnecessary; a pinned action is still third-party code executing within the job's authority.

## 8. Terraform-provider risks

The two root lockfiles are committed and contain checksums for AzureRM `4.81.0`, which is a good control. The broad `~> 4.0` constraint allows every AzureRM 4.x minor when `terraform init -upgrade` refreshes the locks. Review provider changelogs and plans rather than allowing unattended lock regeneration.

The PostgreSQL child module declares Random `~> 3.6`, but no standalone child-module lock is expected; when called by the root, the root should lock all selected providers after initialization. The current root lock contains only AzureRM, indicating the committed lock may not reflect initialization after adding that module/provider. Confirm with a network-enabled, read-only CI `terraform init -lockfile=readonly`; if Random is required and absent, regenerate the root lock in a dedicated reviewed dependency change.

Terraform CLI is exact in GitHub workflows but only broadly constrained in configuration. Provider and CLI major upgrades can change resource schemas, defaults, state upgrades, and plans. The 22 Checkov failures are infrastructure risk independent of provider vulnerability status; making the general scan gating should follow triage and explicit suppressions, not a blind flag change.

## 9. Playwright and browser compatibility

Playwright runner, library and core are aligned at `1.62.1` in the npm lock. CI uses Node 20, `npm ci`, then `npx playwright install --with-deps chromium`; this installs the Chromium revision matched to that Playwright version and is the correct compatibility pattern. Only Chromium is tested: there is no Firefox, WebKit, or real mobile-browser coverage. The Pixel 7 project is Chromium device emulation, not an Android browser/device test.

Do not separately upgrade the browser binary. Upgrade `@playwright/test`, regenerate the npm lock intentionally, install its Chromium revision, and run both desktop and mobile projects. Cache browser binaries only if the cache key includes Playwright's exact locked version.

### Kubernetes API compatibility

Repository-native workload APIs use current stable groups: core `v1`, `apps/v1`, `batch/v1`, `autoscaling/v2`, `networking.k8s.io/v1`, and `policy/v1`. No removed beta native API is visible. Helm charts use chart API `v2`; the two bare `v2` occurrences are `Chart.yaml`, not Kubernetes objects.

The remaining APIs are extension contracts: Argo CD `argoproj.io/v1alpha1`, cert-manager `cert-manager.io/v1`, External Secrets `external-secrets.io/v1`, and Prometheus Operator `monitoring.coreos.com/v1`. Their compatibility depends on CRD/operator versions installed in the cluster, none of which is declared or locked here. Before an AKS or operator upgrade, render the charts and validate against the target cluster's discovery/OpenAPI schemas, confirm each CRD's served and storage versions, and test conversion/migration paths. Static YAML parsing in `platform-security.yml` currently verifies file presence only; it does not perform schema or deprecation validation.

## 10. Upgrade priorities

1. **P0 — release evidence:** run fresh, network-enabled CI scans for both final application images and all dependency manifests; triage the Trivy CRITICAL AKS exposure before a security-sensitive release.
2. **P0 — execution integrity:** pin GitHub Actions and container bases/third-party images by immutable SHA/digest; add the public image to the same gated scanning path.
3. **P1 — Python reproducibility:** constrain the two floating packages, produce reviewed transitive locks with hashes per supported Python version/platform, and split portal runtime from development dependencies.
4. **P1 — infrastructure controls:** reconcile Checkov/Trivy findings, fail on accepted severity levels, and record narrowly scoped suppressions with owners and expiry dates.
5. **P1 — interpreter consistency:** either test Python 3.14 explicitly or keep the public image on the tested 3.12 line until compatibility is proven.
6. **P2 — automation:** enable controlled dependency update pull requests, add npm and Python advisory scans, and retain SBOM/provenance with releases.
7. **P2 — coverage:** consider Firefox/WebKit only if they reflect supported browsers; do not expand merely for version count.

## 11. Safe patch upgrades

No newer version is asserted here because the audit did not query registries. The following are low-risk **classes** of change, each in its own reviewed pull request and subject to the verification plan:

- Align portal Flask from its repository-visible `3.1.1` to the already used `3.1.3` patch after portal and migration tests pass.
- Apply patch-only releases within the existing Python minor and Terraform provider major; refresh locks/hashes intentionally and inspect the complete diff.
- Apply patch releases of the current Playwright line only with its generated lockfile and matched browser installation.
- Refresh base-image digests while retaining the same Python minor and image variant, then rebuild and scan the resulting image.
- Move action tags to reviewed commit SHAs for the exact currently selected releases; this changes provenance without intentionally changing functionality.

These are candidates, not pre-approved changes. A patch may still contain behavior changes and must pass tests and scans.

## 12. Breaking upgrades to defer

Defer until separately planned and tested:

- Terraform 2.x, AzureRM 5.x, or a PostgreSQL major change; these require state/schema, plan, backup, and rollback review.
- Moving all production images from Python 3.12 to 3.14. The public image already creates an unsupported split that should be resolved before broader adoption.
- Playwright major/minor jumps bundled with Node major changes or additional browser engines; snapshot, selector, timing, browser-dependency, and CI image changes can interact.
- Flask, SQLAlchemy, Flask-SQLAlchemy, Flask-Migrate/Alembic, psycopg, Redis, or oauth2-proxy major upgrades; test application behavior, sessions/authentication, migrations, drivers, and rollback independently.
- Kubernetes/AKS major upgrades or CRD major-version changes. Validate operator compatibility and served/stored versions first.

## 13. Verification plan

For every dependency pull request:

1. Review manifest and lock diffs; reject unexpected packages, registries, lifecycle scripts, missing integrity hashes, or unrelated changes.
2. In clean CI, use `npm ci`; install Python from reviewed hash-locked runtime/dev files; use `terraform init -lockfile=readonly` in both roots.
3. Run unit tests (`pytest` for demo, portal, and release tooling) and the full Chromium Playwright suite on the supported Node/Python matrix, including Python 3.14 before retaining it in production.
4. Run `helm lint` and render every production/scale-out values combination. Validate rendered manifests against the target Kubernetes version and installed CRD schemas, not merely YAML presence.
5. Run `terraform fmt`, `validate`, Checkov and plans for both roots; require human review of every resource replacement, state migration, permission expansion, or network exposure.
6. Build every Dockerfile by digest-pinned base, generate an SBOM, scan the final images with a freshly updated database, and enforce the agreed HIGH/CRITICAL policy.
7. Deploy to a non-production environment, execute health, database migration, authentication, public-form, observability and rollback checks; promote the exact tested image digest.
8. Archive test results, plans, SBOM, provenance and scan output with the release. Re-scan deployed digests because advisories can appear after build time.

## 14. Supply-chain controls

- Require immutable GitHub Action SHAs, container digests, protected branches, CODEOWNERS review for workflows/manifests, and environment approval for production.
- Generate hash-locked Python dependency sets from small human-maintained input files; keep runtime and dev/test graphs separate. Continue `npm ci` and reject lockfiles without integrity fields.
- Enable Dependabot or an equivalent updater for npm, pip, Actions, Docker and Terraform, grouping only tightly coupled packages such as Playwright runner/core/browser.
- Generate CycloneDX or SPDX SBOMs for each final image and attach them to releases with provenance attestations. Retain longer than the present 14-day workflow artifact where release/audit policy requires it.
- Sign images/attestations, verify signatures at admission, deploy by digest, restrict tag mutation, and promote the same scanned digest between environments.
- Gate fresh vulnerability and IaC scans. Maintain an exception register containing vulnerability/check ID, affected asset, exploitability, compensating control, owner and expiry.
- Restrict package registries and egress, use trusted mirrors where appropriate, protect publisher credentials with OIDC/short-lived tokens, and minimize job permissions.
- Add Kubernetes schema/deprecation checks against the actual AKS version and policy enforcement for non-root, seccomp, dropped capabilities and read-only filesystems where application writes permit.

## 15. Release blockers

For a security-sensitive application/infrastructure release, block until:

- the local Trivy CRITICAL AKS API-access finding is fixed or formally risk-accepted with time-bound compensating controls;
- fresh CI advisory databases confirm no unaccepted runtime HIGH/CRITICAL vulnerabilities in **both** final images and Python manifests;
- the five local HIGH workload-security findings and the 22 Checkov failures are triaged, with fixes or documented, expiring exceptions;
- Python 3.14 compatibility for the public image is demonstrated or that image is returned to the tested interpreter line;
- the public image receives the same image vulnerability gate as the main image; and
- the Terraform lock is verified read-only, including whether the Random provider must be recorded at the root.

Mutable Action/base-image references and missing Python transitive locks are high-priority hardening work. Treat them as blockers where the organization's release policy requires reproducible builds or SLSA-style provenance. They do not, by repository evidence alone, prove a present compromise.

## 16. Recommended recurring audit cadence

- **Every pull request:** lock/manifest diff review, tests, Helm/schema validation, Terraform validation/plan and fresh dependency/IaC/image scans for affected components.
- **Daily:** re-scan production image digests and alert on newly disclosed HIGH/CRITICAL issues; ingest GitHub/registry advisories.
- **Weekly:** automated dependency update pull requests, CodeQL (already scheduled Mondays), failed-scan review, and expiring-exception review.
- **Monthly:** patch window for Python, npm/Playwright, Actions, providers, base images and third-party workload images; refresh SBOMs and verify restore/rollback artifacts.
- **Quarterly:** full supply-chain review covering unused/runtime classification, permissions, registries, signatures, provenance, Kubernetes API deprecations, Terraform/provider release notes and disaster recovery.
- **Before every release and immediately after a critical advisory:** scan the exact release/deployed digests with current databases and repeat targeted regression/rollback verification.

## Audit limitations

This audit deliberately made no network-dependent claim. It did not query npm/PyPI/GitHub/container registries, modify lockfiles, install packages, build or pull images, deploy, or inspect external CI/security dashboards. “No vulnerability found” means only “not found by the named local tool and cached database at audit time.” Unused-dependency conclusions are based on repository imports and build paths: pytest is visibly dev-only in the portal requirements, npm is visibly test-only, and no other direct runtime dependency is demonstrably unused from static inspection alone.
