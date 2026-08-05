# Traditional Strength platform roadmap

The roadmap separates delivered Version 1 scope from future reliability and product evolution. A future-version item is not an implied current capability.

## Version 1 — production foundation (complete)

Status: **Complete and validated**

- Production application reachable over HTTPS with a healthy `/health` endpoint.
- Argo CD Application Synced and Healthy.
- Terraform-managed Azure resources and AKS with remote state.
- Separate AKS System and production User pools with workload node selection.
- Private PostgreSQL Flexible Server, private DNS, and VNet peering.
- Key Vault, Workload Identity, and External Secrets runtime delivery.
- Immutable images, Helm release, Argo CD reconciliation, and CI/CD validation.
- Production security contexts, NetworkPolicies, probes, migration gating, and runbooks.

Version 1 has one recorded deferred control: production-pool host encryption is blocked by East US 2 vCPU quota. This does not reopen Version 1 scope; it is a tracked hardening action with explicit exit criteria in [production-backlog.md](production-backlog.md).

## Version 2 — reliability, hardening, and promotion

Version 2 improves the operating model without changing the core product architecture:

- obtain Azure quota, rotate the production node pool safely, enable host encryption, and remove `CKV_AZURE_227`;
- validate database concurrency and enable the reviewed scale-out overlay;
- define SLIs/SLOs and activate tested metrics, dashboards, alerts, and notification routing;
- perform and record PostgreSQL point-in-time restore, application rollback, and node-failure exercises;
- introduce a staging environment and protected promotion pull requests;
- evaluate PostgreSQL HA, longer retention, and geo-backup against explicit RPO/RTO and cost;
- add signed images, provenance, and admission verification;
- design Azure Front Door/WAF and a private origin;
- automate quota, capacity, dependency, certificate, and cost review.

Exit criteria: a tested staging-to-production promotion, two-replica production operation, actionable alert delivery, a recorded recovery exercise, and closure or formally re-acceptance of Version 1 security backlog items.

## Version 3 — scalable product platform

Version 3 evolves the platform for broader product usage and stronger failure isolation:

- multi-region recovery or active/passive service architecture with tested failover;
- stronger user, coach, and service identity boundaries and auditable authorization;
- event-driven workers and durable queues for asynchronous coaching workflows;
- analytics and reporting designed around approved data-retention and privacy controls;
- independent service scaling where measured load justifies decomposition;
- platform APIs and reusable deployment patterns for additional Traditional Strength services;
- capacity and cost automation based on SLOs, demand, and recovery requirements.

Exit criteria will be defined from measured Version 2 usage and business requirements. Version 3 is intentionally not a promise of microservices, service mesh, or multi-region active/active operation without evidence that the complexity is justified.
