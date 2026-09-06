# Limitations and future improvements

## Scope

Traditional Strength Version 1 is a production platform and portfolio project, not an enterprise landing zone or a multi-region business-critical service. [roadmap.md](roadmap.md) separates completed Version 1 work from Version 2 and Version 3.

## Current limitations

### Single Azure region

The platform runs in East US 2. A regional outage can make the application and database unavailable. Multi-region recovery, traffic management, replicated state, and failover exercises are Version 3 work.

### Public AKS control plane

The AKS API is public with authorized IP ranges and Kubernetes/Azure controls; it is not a private cluster. A private control plane would require private DNS plus a tested operator and CI access path.

### Public ingress without WAF

NGINX is the public HTTPS entry point and the Flask Service is `ClusterIP`. Azure Front Door/WAF and a controlled private origin are not implemented.

### Single application replica during cutover

Production deliberately runs one replica with HPA disabled while PostgreSQL cutover behavior is validated. The chart contains topology preferences and an opt-in scale-out overlay, but these do not provide current high availability. Version 2 requires concurrency, connection-pool, failure, and recovery evidence before scale-out.

### Production-pool host encryption deferred

The System pool has host encryption. The production User pool does not because Azure could not allocate the temporary two-vCPU rotation node after East US 2 regional quota was exhausted. The exact `CKV_AZURE_227` exception and completion criteria are in [production-backlog.md](production-backlog.md).

### Cost-conscious PostgreSQL resilience

Flexible Server uses private networking, TLS, auto-grow, and automated point-in-time backups. High availability and geo-redundant backup are disabled. Recovery objectives and a recorded restore exercise remain Version 2 requirements.

### No complete environment promotion model

Production desired state is protected through Git and Argo CD, but the repository does not provide a complete development-to-staging-to-production promotion path with equivalent environment Applications and approval evidence.

### Monitoring is incomplete

The application exposes health and metrics and the Azure monitoring foundation exists. Proposed ServiceMonitor, PrometheusRule, and Grafana dashboard resources are disabled in production until real labels, storage, authentication, notification routing, and failure behavior are validated. Paid-beta SLOs and an error budget are now defined in [paid-beta-slos-and-python-skips.md](paid-beta-slos-and-python-skips.md), but they are entry criteria rather than achieved SLOs until measurement and alert delivery are proven.

### Supply-chain enforcement is incomplete

CI performs dependency/code analysis, vulnerability and misconfiguration scanning, immutable image validation, and SBOM generation. Images are not signed and the cluster does not enforce signatures or provenance at admission.

### Recovery and regional resilience are not proven

Terraform and Git can reconstruct much of the platform, and PostgreSQL provides managed backup capability, but formal RTO/RPO, a tested application/database restore, and regional failover evidence are not complete.

### Cost-driven capacity

Small pools, a burstable database SKU, single-region deployment, and limited telemetry retention control portfolio cost. Quota and capacity must account for upgrade/rotation surge as well as steady-state workload.

### Programme hierarchy stops at blocks

Programming currently models blocks, weeks, sessions, lift slots, and exercise prescriptions. It has no macrocycle entity or lifecycle, so cross-block macrocycle planning is future domain work rather than a label layered onto blocks. A future design must first define ownership, ordering, publication, archive, revision, and completed-history semantics.

## Priorities

1. Close the host-encryption quota backlog and validate safe node-pool rotation.
2. Test database recovery and application scale-out, then enable multiple replicas.
3. Establish SLOs and verified monitoring/alert delivery.
4. Add staging and a protected promotion model.
5. Add image signing/provenance and evaluate WAF/private-origin architecture.
6. Define multi-region recovery only from measured business requirements.

See [roadmap.md](roadmap.md) for version ownership and exit criteria.

## Future V6 and SaaS boundary

No current manifest, Terraform resource or application model establishes a
multi-tenant SaaS control plane. A future V6/SaaS description must therefore be
treated as product architecture work, not an extension already provided by the
current AKS deployment. The following are not evidenced as implemented:

- tenant-scoped identity, authorization and database isolation;
- tenant provisioning, lifecycle, quotas or per-tenant configuration;
- subscription billing, metering or entitlement enforcement;
- tenant-specific encryption keys, backup/restore or data residency;
- auditable administrative impersonation and support access;
- per-tenant SLOs, cost attribution and noisy-neighbour controls; and
- a migration path from the shared Flask/PostgreSQL deployment to those
  boundaries.

Future design should begin with business tenancy and data-isolation
requirements. It should not assume microservices, multiple clusters or a
service mesh until those requirements and measured load justify them.
