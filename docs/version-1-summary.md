# Version 1 summary

## What Version 1 delivers

Version 1 delivers a functioning production platform for Traditional Strength rather than a diagram-only reference implementation. The public application is healthy, Argo CD reports the production Application Synced and Healthy, and the deployed state is expressed through Terraform, Helm, Kubernetes manifests, and GitHub workflows.

The release includes:

- Terraform-managed Azure infrastructure with independent root and AKS states;
- AKS with isolated system and production User node pools;
- production workload placement through `workload=production`;
- private Azure PostgreSQL Flexible Server connectivity through delegated networking, private DNS, and VNet peering;
- database migrations as a Helm pre-install/pre-upgrade Job;
- Key Vault secrets delivered through Workload Identity and External Secrets;
- immutable ACR images, Helm packaging, and Argo CD automated sync, pruning, and self-healing;
- application, Terraform, browser, security, dependency, tooling, and release validation in GitHub Actions; and
- health checks, telemetry foundations, security contexts, NetworkPolicies, and operational runbooks.

## Major engineering decisions

### Separate Terraform states

Shared infrastructure and AKS use separate Terraform roots and Azure Storage backends. This limits blast radius and lets cluster changes be reviewed independently. Existing Azure resources were imported rather than recreated. State and saved plans are treated as sensitive because the generated database password is necessarily present in state.

### Separate AKS pools

Cluster-critical services remain on the System pool. Application and migration workloads select the autoscaling production User pool. This protects system capacity and creates a clear place for application-specific sizing and hardening.

### GitOps owns deployment

CI builds, tests, scans, publishes, and updates the immutable image tag in Git. Argo CD deploys and continually reconciles the Helm release. This avoids granting a general CI process ownership of ad hoc `kubectl` changes and makes the production desired state reviewable.

### Private managed database

PostgreSQL Flexible Server replaces local-file persistence for production. Public network access is disabled. A delegated subnet, private DNS links, and bidirectional VNet peering allow AKS to reach the database by its private FQDN with TLS.

### External secret synchronisation

Key Vault remains the secret source of truth. External Secrets uses Workload Identity and materialises only the Kubernetes Secret required by the workload. Helm values carry secret references, not values.

### Safe database cutover

Production deliberately starts with one replica and HPA disabled. A no-retry migration hook runs the exact release image before the Deployment. The separate scale-out overlay is an explicit second decision after connectivity, migration, connection-pool, and recovery checks.

## Production incidents and problems solved

The final platform reflects real integration work:

- Imported PostgreSQL resources exposed Azure-assigned availability-zone drift. Terraform now ignores the service-assigned `zone` field to avoid a false replacement after import.
- The private PostgreSQL server was initially unreachable from AKS. Terraform now manages both VNet peering directions and the AKS private-DNS-zone link.
- The application initially lacked the production database key. The ExternalSecret now maps `database-url` to `DATABASE_URL` in `flask-runtime-secrets`.
- Helm refactoring risked changing the existing production ingress identity. The production value preserves the deployed `flask-web-prod` ingress name.
- Application workloads previously shared cluster capacity with system services. A labelled production User pool and chart `nodeSelector` now enforce placement.
- Enabling host encryption on that new pool required a temporary rotation node. Azure rejected it because East US 2 regional vCPU quota was exhausted; the change was safely deferred rather than forcing a disruptive workaround.

## Final validated state

| Validation | Result |
| --- | --- |
| Argo CD `flask-web-production` | Synced and Healthy |
| Public health | `https://traditionalstrength.co.uk/health` returns healthy |
| Infrastructure ownership | Terraform-managed |
| AKS scheduling | System pool plus production User pool; application selects production |
| Database exposure | Private Flexible Server; public access disabled |
| AKS database path | Private DNS and VNet peering implemented |
| Runtime secrets | Key Vault to External Secrets to Kubernetes Secret |
| Release model | Immutable image, Helm, Argo CD GitOps |
| Validation model | GitHub Actions application, Terraform, security, browser, tooling, and release workflows |

## Deferred security hardening

The production User pool does not yet have host encryption enabled. The exception is limited to `CKV_AZURE_227` on that resource and explains the attempted change, the temporary-node requirement, and the exhausted East US 2 vCPU quota. [production-backlog.md](production-backlog.md) defines the completion steps: obtain quota, configure the rotation name, enable encryption, confirm a non-destructive plan, apply, and remove the exception.

Other roadmap hardening includes a private AKS control plane, WAF/private-origin architecture, image signing and admission verification, tested alert delivery, stronger recovery objectives, PostgreSQL HA/geo-backup where justified, and multi-region recovery. These are not presented as Version 1 capabilities.

## Lessons learned

- Importing infrastructure is the beginning of reconciliation, not the end; provider-computed attributes and replacement behavior must be reviewed carefully.
- Private networking requires DNS, routing, and application configuration to succeed together. A private server alone does not establish connectivity.
- Database migrations need to be part of release orchestration and use the same immutable artifact as the application.
- GitOps works best when CI and CD responsibilities are explicit and manual cluster changes are treated as drift.
- Secret management is a flow involving identity, authorization, refresh, and consumption—not merely a vault resource.
- Workload isolation must be expressed at both infrastructure and Kubernetes layers: a User pool is ineffective without scheduling constraints.
- Security exceptions should record a specific control, failed remediation evidence, owner action, and removal criteria.
- Cloud quota is a production dependency. Capacity for surge and rotation operations must be included in change planning, not just steady-state sizing.
