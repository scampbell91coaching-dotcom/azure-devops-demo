# Operations, recovery and release controls

## Operating model

Git is the desired-state authority. Routine application changes promote a
commit-SHA image by changing the tracked Helm value or raw private-platform
manifest; Argo CD reconciles it with pruning and self-healing. Direct `kubectl`
or Helm mutations are temporary diagnostics or containment and will not survive
reconciliation.

This document describes procedures present in the repository. Commands that
read a live environment require separate authorization and were not run while
producing this documentation.

## Release gates

| Change path | Pull request / validation gates | Main / release behavior |
| --- | --- | --- |
| Public application | Helm lint/render for cutover and scale-out, secret-boundary assertions, pytest, image build and blocking Trivy scan | OIDC login, immutable image push, Git promotion commit, AKS selected-image/rollout check, public `/health` check |
| Private portal | kubeconform, manifest assertions, pytest, Playwright, image build and blocking Trivy scan | OIDC login, immutable image push, Git promotion commit, rollout/database/internal-health verification and anonymous-edge redirect check |
| Terraform | format, offline init/validate and Checkov | root and AKS plans; one-day plan artifacts; production-environment apply of those artifacts |
| Cross-cutting security | KeePass exclusion, Helm and observability rendering, Trivy filesystem vulnerability/secret/misconfiguration scan, SBOM | Same path-scoped controls on `main` |
| Additional | CodeQL, browser suite, toolchain audit/update workflows | Triggering and enforcement depend on path filters and external branch protection |

These workflows demonstrate available gates, not that GitHub branch protection,
required checks or production environment reviewers are configured. The release
checklist also requires change approval outside the repository.

## Migration gating

The public chart runs `flask db upgrade` as a no-retry Helm
`pre-install,pre-upgrade` hook using the candidate image and migration Secret.
The private Application runs an Argo CD `PreSync` Job using both occurrences of
the same candidate private image; it upgrades, seeds idempotent catalog data and
verifies the production database. Hook success gates the associated rollout.

The repository does not automate schema downgrade. Migrations must remain
compatible with the previous application version if an image rollback is to be
safe.

## Application rollback

Preferred rollback:

1. identify the bad promotion commit and previous immutable image;
2. assess whether its schema change remains compatible with the previous image;
3. revert the promotion commit through the normal Git review/approval path;
4. let Argo CD reconcile and verify the exact image, rollout and health; and
5. record the incident and corrective release.

`kubectl rollout undo` is only emergency containment. Automated self-healing can
restore the Git-declared image. Do not automatically run Alembic downgrade or
restore PostgreSQL merely to match an older image; either is a separate,
data-affecting recovery decision.

Detailed commands are in the [operational runbook](runbook.md) and the
[rollback template](release/rollback-plan.md).

## PostgreSQL backup and PITR

Implemented configuration:

- Azure PostgreSQL Flexible Server managed backups;
- retention constrained to 7–35 days and tracked as seven days;
- PostgreSQL `prevent_destroy` in Terraform;
- geo-redundant backup disabled in tracked values;
- high availability disabled in tracked values.

Repository procedure, not automated implementation:

1. choose an approved UTC restore point within retention;
2. restore to a **new** Flexible Server using the Azure CLI;
3. establish its delegated-subnet/private-DNS connectivity;
4. validate schema and data without exposing connection values;
5. prepare runtime and migration URLs in Key Vault;
6. allow External Secrets to reconcile, then promote the connection change;
7. verify migrations, application reads/writes and health; and
8. preserve the source until the recovery is accepted.

There is no restore workflow, DNS cutover automation, recorded database restore
exercise or formal RPO/RTO in the repository. Therefore PITR capability is
configured, while DR readiness is unproven. The committed pod-deletion evidence
tests Kubernetes replacement behavior only; it is not database or regional DR
evidence.

## Failure domains and recovery posture

| Failure | Repository response | Limitation |
| --- | --- | --- |
| Pod/process failure | probes, Deployment replacement and rolling strategy | Production declares one replica, so continuity is not assured |
| Bad application image | immutable prior tag plus Git revert | schema compatibility must be assessed |
| Failed migration | hook blocks rollout; failed job retained temporarily | no automatic repair or downgrade |
| Secret synchronization failure | ExternalSecret/SecretStore diagnostics in runbook | application depends on existing Kubernetes Secret; no alternate secret path |
| Node failure | User-pool autoscaling and scheduler replacement | private raw workloads do not explicitly select the User pool |
| Database corruption/operator error | managed PITR to a new server | restore and connection cutover are manual and untested here |
| Region failure | none | single-region platform and non-geo backups |
| GitOps control failure | diagnose Application/diff; workloads continue at last state | no documented Argo CD backup/bootstrap automation |

## Safe verification

Never print or decode Secrets, Terraform state, saved plans, OIDC tokens or
connection strings. Evidence should contain only resource names, revisions,
health/status, image references and sanitized command outcomes.

Useful local checks are documented in the root README. Live checks, when
authorized, should establish separately:

- Argo CD sync and health for each Application;
- exact Deployment image equals Git desired state;
- migration Job outcome and current Alembic head;
- ExternalSecret readiness without reading target values;
- private DNS and TCP 5432 reachability from an approved diagnostic pod;
- public health and private anonymous redirect behavior; and
- backup inventory and a separately approved restore exercise.

## Future operational boundary

Staging promotion, two-replica validation, active alert routing, restore drills,
formal RPO/RTO, signed-image verification, multi-region recovery and SaaS
tenant operations are planned work. See [Roadmap](roadmap.md).
