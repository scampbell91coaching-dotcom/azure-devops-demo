# Azure cost and capacity audit

## Scope and evidence boundary

This is a documentation-only audit of the Traditional Strength repository as at
3 August 2026. It describes Terraform, Kubernetes/Helm and GitHub Actions
configuration; it does **not** confirm deployed Azure inventory, utilisation,
prices, bills, quotas or service health. No Azure API, Terraform plan/apply or
deployment was used for this audit.

The configuration has two independently managed Terraform states: the root
stack in `infra/` and AKS in `infra/aks/`. References to resources as “defined”
below mean defined in source, not necessarily deployed. Existing resources read
as Terraform data sources (the resource group, ACR and optionally Key Vault) and
the remote-state storage account must be verified separately against an
authorised inventory and bill.

## Executive summary

The recurring cost is most likely dominated by always-on AKS worker VMs,
PostgreSQL Flexible Server when enabled, and telemetry ingestion. Storage,
registry, public IP/load-balancer processing, backups and CI minutes are smaller
but can accumulate. The lowest-cost safe V1 is a single non-production
environment, one modest AKS system pool node where workload and upgrade tests
prove it fits, Basic ACR, one application replica, the current burstable
PostgreSQL starting point, minimum supported database storage and backup
retention, and tightly sampled/capped telemetry. A public production service
should normally keep two nodes and two application replicas for failure and
maintenance tolerance; that availability choice has a real, deliberate cost.

The largest immediate repository-level opportunity is to make the AKS capacity
intent coherent: dev tfvars specifies two fixed `Standard_D2s_v3` nodes while
the declared `min_node_count` and `max_node_count` are unused because cluster
autoscaling is disabled. Rightsizing must follow measured requests, peak usage,
daemon-set overhead and an upgrade simulation, not VM price alone.

## Current architecture and cost drivers

| Area | Repository evidence | Cost driver or exposure |
|---|---|---|
| AKS | Free control-plane tier; one `system` VMSS pool; Azure CNI/policy; Standard load balancer; fixed node count | Worker VM compute and 30 GiB OS disks are continuous. Load-balancer rules/data and outbound data can add cost. Free tier has no paid control-plane SLA. |
| Application | `flask-web` production values: one replica, HPA off, 250m CPU/256 MiB request, 750m/512 MiB limit | Requested resources determine schedulable capacity; one replica is cheap but interruption-prone. A migration Job runs per release. |
| Lead magnets | One replica, 50m CPU/96 MiB request, 1 GiB RWO PVC | Small compute footprint; PVC persists and bills independently of pod use. SQLite on one RWO volume limits horizontal scaling. |
| Supporting workloads | In-cluster ingress/GitOps/monitoring are described; Redis declares 25m CPU/64 MiB and ephemeral data | System add-ons and daemon sets consume node headroom even when application traffic is low. |
| PostgreSQL | Optional Flexible Server with private networking, PostgreSQL 16 default, burstable `B_Standard_B1ms`, 32 GiB, auto-grow, seven-day backup, no geo backup, no HA | Compute while running, provisioned storage, backup consumption and private DNS. Auto-grow is one-way capacity growth and can create lasting spend. HA approximately adds a standby compute/storage footprint and is intentionally off. |
| Registry | Basic ACR, admin disabled | Registry capacity, stored layers, build/pull traffic and unpruned image history. |
| Observability | Workspace-based Application Insights; Log Analytics `PerGB2018`, 30-day retention; Linux DCR at 60 seconds plus warning-and-higher syslog; in-cluster Prometheus at three days | Ingested GB, retention beyond included terms where applicable, queries/exports/alerts, and Prometheus CPU/memory. Application Insights can duplicate signals already held in Prometheus. |
| Network/public edge | VNet `/16`, delegated database `/24`, private DNS; AKS Standard load balancer/outbound; ingress uses public HTTPS | VNet/subnet themselves are not the main charge; public IP, load balancer processing, NAT/egress, cross-region and Internet egress may be. The exact public IP inventory is not declared. |
| Storage/backups | 30 GiB AKS OS disk per node; 1 GiB lead-magnet PVC; PostgreSQL data/backups; Azure Storage remote backend referenced | Persistent disks, snapshots/backups, transaction growth and retained Terraform state. The backend storage account is referenced, not provisioned here. No general-purpose application storage account is defined. |
| CI/CD | GitHub-hosted Ubuntu jobs, Docker builds, security scans, Playwright browser installs, Terraform init/plan/apply jobs and short-lived artifacts | Runner minutes, repeated dependency/browser downloads, registry writes and artifact storage. Entitlement and billing depend on repository/organisation plan. |

Application Insights availability tests and KQL alert definitions in
`docs/production-observability.md` are explicitly proposed, not provisioned.
Likewise, repository screenshots and evidence are not an authoritative current
inventory.

## Resources already defined

The root Terraform defines a resource group, VNet, delegated PostgreSQL subnet,
Log Analytics workspace, workspace-based Application Insights component, Linux
data collection rule and Basic ACR. When explicitly enabled it also defines a
PostgreSQL Flexible Server, database, private DNS zone/link, generated
administrator password and five secrets in an existing Key Vault. PostgreSQL
has private-only access, TLS 1.2, Sunday 03:00 maintenance, auto-grow and
`prevent_destroy`.

The separate AKS Terraform defines an AKS Free-tier cluster, one fixed system
node pool, system-assigned identity, OIDC/workload identity, Key Vault CSI
provider, Azure network policy, Standard load balancer and ACR pull role. It
does not define a user node pool, cluster autoscaling, NAT gateway, explicitly
managed public IP, Container Insights attachment, availability zones, budgets
or cost alerts. `min_node_count` and `max_node_count` variables currently have
no effect.

Kubernetes/Helm defines the application, lead-magnet service and PVC, ingress,
network policies, an ephemeral Redis session store, and an optional
Prometheus/Grafana/Alertmanager stack. The production Flask release is one
replica with HPA disabled; the opt-in scale-out overlay is two to five replicas
at 50% CPU. The generic chart default is one to five replicas at 50% CPU.

## Cost assumptions

The following are assumptions for estimation and decisions, not observed facts:

- V1 traffic is low and variable; most hours are idle or lightly loaded.
- One region is acceptable for V1 and development does not require an uptime SLA.
- The application fits within its declared requests and a modest node after AKS
  system, ingress, GitOps and monitoring overhead is included.
- PostgreSQL data initially fits within 32 GiB and burstable CPU credit behaviour
  is acceptable after load testing.
- Seven-day point-in-time recovery and locally redundant backup satisfy the V1
  recovery policy; no compliance rule requires longer or geo-redundant retention.
- GitHub-hosted runner usage is within the organisation's included allowance;
  this must be checked against the actual GitHub plan.
- No reservations, savings plan, dev/test pricing, negotiated discounts, taxes
  or Azure free credits are assumed.

Do not turn these into purchase decisions until the Azure Pricing Calculator is
run for the deployment region and actual usage is exported by meter/category.

## Lowest-cost safe Version 1

For a development/demo V1, keep one region and one environment; Basic ACR; one
application and one lead-magnet replica; no database HA or geo backup; 32 GiB
PostgreSQL storage with seven-day retention; private database access; and short
Prometheus retention. Start with one appropriately sized AKS node only after a
rendered workload request total plus daemon-set overhead and upgrade surge fits
with at least 20% memory and CPU headroom. Schedule the non-production cluster
and database off outside working hours where Azure service capabilities,
recovery time and team access patterns make that safe.

For an Internet-facing production V1, the lowest safe baseline is usually two
nodes across zones where supported, two web replicas with disruption controls,
and HPA minimum two. Keep PostgreSQL single-instance only if the documented RTO
accepts restart/failover downtime; otherwise pay deliberately for eligible GP
compute and HA. Do not represent the current one-replica/fixed-pool layout as
highly available.

## Development versus production

| Decision | Development | Production |
|---|---|---|
| Lifecycle | Stop/deallocate on a schedule; recreate disposable environments | Always on unless the product explicitly accepts scheduled downtime |
| AKS | One small node if validated; Free tier; fixed size is simplest | Two-node minimum for maintenance/failure tolerance; evaluate Standard tier/SLA from business requirement |
| Web replicas | One; HPA off | Two minimum and HPA on after DB cutover and load test |
| PostgreSQL | Burstable B1ms starting point, 32 GiB, 7 days, no HA/geo | Start B1ms only for genuinely small load; move to GP before burst credits or latency breach SLO; HA/geo follow RTO/RPO |
| Telemetry | Sampling, warning/error focus, short retention; avoid duplicate verbose traces | Adaptive/fixed sampling with exceptions and critical transactions retained; ingestion cap and alerting |
| Data | Synthetic/minimised data; short lifecycle | Tested restore, explicit retention and legal requirements |
| CI | Path filters, concurrency cancellation, manual expensive checks | Required release/security checks; avoid duplicate runs without weakening gates |

## AKS node-pool and workload capacity recommendations

1. Measure per-container CPU/memory working set, throttling, OOMs, pending pods,
   daemon-set requests and node allocatable capacity for at least a representative
   peak period. Compare p95 usage with requests; change requests gradually.
2. Resolve the current inconsistency: either keep a deliberately fixed pool and
   remove misleading min/max settings, or enable cluster autoscaling and wire
   them into the pool. A min and max both equal to one would not autoscale.
3. In dev, test one `Standard_B2s`-class node (the module default) against burst
   credit exhaustion and memory pressure; the committed dev override is two
   `Standard_D2s_v3` nodes. SKU availability and price must be checked in East US
   2 at decision time.
4. In production, prefer a small system pool for critical add-ons and a separate
   autoscaled user pool only when workload scale or isolation justifies the
   extra minimum node. At V1 scale, an extra always-on pool can cost more than it
   saves; use taints/priority and careful capacity instead.
5. Preserve headroom for rolling upgrades (`max_surge = 10%` can still require
   an additional node), pod surge, drain and zone failure. Validate PodDisruptionBudget
   behaviour and max-pod/IP capacity before downsizing.
6. Consider Spot only for interruptible jobs, never as the sole capacity for the
   web tier, ingress, DNS, GitOps or migrations.

Workload starting thresholds: target steady p95 CPU below 60% of request and p95
memory below 70% of limit, investigate sustained node CPU above 70%, memory above
75%, disk pressure, any recurring pending pods, OOM kills or CPU throttling. For
the web HPA, start at two to five replicas and 60% CPU, retain a five-minute
scale-down window, and scale up by no more than two pods per minute. The existing
50% setting is safer but potentially more eager; choose after a load test. Add a
latency/request-rate metric if CPU does not correlate with demand. Scale the
node pool only after pod autoscaling is functional and Metrics Server is reliable.

## PostgreSQL, storage and backup recommendations

`B_Standard_B1ms`, 32 GiB and auto-grow are sensible V1 defaults for low duty
cycle development and a very small production database. Burstable compute is
not a safe default for sustained CPU: monitor CPU credits, connections, memory,
IOPS, storage percentage, query latency, locks and replica/backup health. Move
to the smallest General Purpose SKU supported in-region when credits regularly
deplete, p95 database latency breaches the SLO, memory/connection pressure is
sustained, or HA is required. Do not size from CPU alone.

Keep 32 GiB until forecast growth or observed utilisation requires more. Alert
at 70% used (forecast/review), 80% (capacity action) and 90% (urgent). Auto-grow
prevents an immediate full-disk incident but can permanently raise the bill; it
is not a capacity plan and should trigger review. Avoid provisioned IOPS or
larger storage solely for theoretical performance. Test query/index optimisation
first and verify storage downsizing limitations before allowing growth.

Seven-day automated backup retention is the lowest configured and supported
repository setting and minimises retained backup exposure. It gives a short
point-in-time restore window and may fail business, deletion-recovery or legal
needs. Increase toward 14–35 days only from a documented recovery requirement.
Geo-redundant backup improves regional disaster recovery at added cost and may
be constrained by region; enable it for a stated regional RPO, not as a default.
HA improves availability but is not a backup. For long-term retention, use a
separately governed logical/archive process with restore tests, immutability and
expiry rather than extending every hot operational backup indefinitely. Test a
restore at least quarterly and before reducing retention.

The lead-magnet 1 GiB PVC contains SQLite data: unused PVCs can survive pod or
release deletion, while RWO/SQLite constrains scale and availability. Document
its backup and deletion policy. Redis is deliberately ephemeral and must not be
treated as a backup or durable session database.

## Observability ingestion controls

- Set an explicit Log Analytics daily cap with an alert before the cap; understand
  that hitting it creates monitoring blind spots. Use a budget as the primary
  guardrail and the cap as emergency containment.
- Configure Application Insights sampling by telemetry type. Retain all
  exceptions and critical business/security events; sample successful requests,
  dependencies and verbose traces. Exclude health probes and known noise where
  operationally safe.
- Add table-level retention appropriate to incident and audit needs rather than
  applying 30 days indiscriminately. The Terraform currently fixes workspace
  retention at 30 days and declares no daily cap.
- Review the Linux DCR before association: 60-second wildcard disk counters and
  all facilities at warning-or-higher may be noisy. Collect only actionable
  counters/facilities and avoid sending the same Kubernetes signal through both
  Prometheus and Log Analytics.
- Keep Prometheus at three days for V1 if it meets troubleshooting needs;
  persistence is disabled, so restarts lose history. Increase retention or add
  remote storage only for a defined diagnostic/SLO requirement.
- Alert on ingestion volume/day, rejected/capped data, unexpected table growth
  and telemetry cost per 1,000 requests. Review sampling after incidents.

## Idle-resource and leakage risks

Check through an authorised, read-only inventory process: unattached managed
disks and NICs; orphaned public IPs/load balancers; old PVCs/snapshots; stopped
but allocated VMs; unused AKS clusters/node pools; idle PostgreSQL servers;
unassociated DCRs; stale workspaces; obsolete ACR layers/manifests; old backup
vault items; private endpoints/DNS zones; and forgotten dev resource groups.
Repository-specific risks include two Terraform states drifting independently,
the externally managed Key Vault and state storage account, implicitly created
AKS networking resources in the node resource group, and GitOps-created
resources absent from Terraform inventory.

Create a monthly orphan report and require owner confirmation before deletion.
ACR retention/purge policies must protect deployed immutable digests and rollback
images. Never delete storage, backups, public IPs or registry content from name
alone.

## GitHub Actions usage patterns

Path filters already avoid many irrelevant runs, browser tests and application
CI cancel superseded runs, job timeouts are present in several workflows, and
artifacts retain for 1, 7 or 14 days. These are cost-conscious defaults.

Potential duplication remains: a main-branch application change can run unit
tests/build/push/promotion/smoke testing, browser tests, lead-magnet build/push,
and security work depending on paths. The Terraform workflow performs quality,
two plans and two apply jobs on every matching push to main; PostgreSQL has a
separate validation/plan workflow. Docker builds can therefore publish two
images from the same `platform-portal/**` change. CodeQL also runs weekly.

Track billable minutes by workflow/job, queue time, cache hit rate and failed or
cancelled minutes. Add concurrency cancellation to safe plan/security/build
jobs, pin reasonable timeouts everywhere, cache immutable dependencies and
Docker layers, and consolidate duplicate validation only when required security
coverage remains. Use path filters carefully: shared dependency or workflow
changes must still trigger all affected tests. Keep artifacts only as long as
audit/debug needs require. Do not replace GitHub-hosted runners with an always-on
self-hosted VM until measured minutes, security isolation and maintenance cost
justify it.

## Budgets, alerts and monthly estimation

Define Azure Cost Management budgets as code at subscription and
environment/resource-group scope with non-blocking notifications at 50%, 75%,
90% and 100% of the monthly target, plus a forecast alert at 100%. Route to a
named owner and backup owner; budgets notify but do not stop spend. Add anomaly
review and service-specific operational alerts for node saturation, database
storage/credits and telemetry ingestion. Separate production and development
budgets, and use an action group with tested email/ChatOps routing. No budgets or
cost alerts are currently defined in this repository.

Estimate monthly cost without inventing a live number:

1. Export the intended Terraform plan/resource inventory without applying it,
   then reconcile it with an authorised Azure inventory and last three complete
   billing months. Include the AKS-managed node resource group.
2. In the Azure Pricing Calculator, select the actual region/currency and model
   `hours/month × node count × VM rate`, OS/data disks, AKS tier, load balancer,
   public IP and expected egress.
3. Add PostgreSQL compute hours, provisioned storage/IOPS, retained backup above
   included allowance where applicable, HA/geo options and private networking.
4. Add ACR tier/storage/egress, Log Analytics and Application Insights GB/day ×
   days plus retention/export/alert charges, and all PVC/storage accounts.
5. Add GitHub billable runner minutes and artifact/package storage using the
   organisation's actual plan and included allowance.
6. Model low/base/peak scenarios and development schedules. Apply current Azure
   agreement discounts, reservations/savings plans, tax and currency only after
   the raw usage model is visible.
7. Compare forecast with actual cost by service and tag monthly. Explain variance
   from quantity, rate, new resources, ingestion and commitment coverage; update
   the model rather than hiding variance in contingency.

Record calculator date, price source, region, SKU, hours, quantities, utilisation
assumptions and excluded taxes/discounts. Prices change, so this method is more
durable than embedding an exact monthly total here.

## FinOps tags and allocation

Apply a consistent tag map through every Terraform module rather than the current
mixed casing/values. Recommended required tags are `Environment`, `Application`,
`Service`, `Owner`, `CostCenter`, `ManagedBy`, `Criticality`, `DataClassification`,
`Lifecycle`, and `BusinessHours` (where scheduling applies). Suggested values
include `Application=traditional-strength`, `ManagedBy=terraform`, an accountable
team/email for `Owner`, and `Lifecycle=permanent|ephemeral`.

Enforce presence and allowed values with Terraform validation and Azure Policy,
but account for resource types and AKS-managed resources that do not inherit tags
automatically. Resource-group tags are not automatically inherited for billing.
Propagate tags to AKS node resource group/VMSS where supported, PostgreSQL,
workspace, Application Insights, ACR, disks, public IPs and storage. Keep
cost-allocation tags free of personal or sensitive data. Review untagged spend
monthly and map shared platform cost with a documented allocation rule.

## Prioritised savings

| Priority | Action | Expected effect | Safety gate |
|---|---|---|---|
| 1 | Reconcile actual inventory/bill with both Terraform states and AKS node resource group | Finds orphaned and unallocated spend; establishes baseline | Read-only inventory, owner confirmation |
| 2 | Measure and rightsize the fixed two-node `D2s_v3` dev pool; schedule non-production | Targets the likely largest idle cost | Peak/load/upgrade test and 20% headroom |
| 3 | Add telemetry sampling, noise exclusions, ingestion alerts and a reviewed cap | Controls an unbounded variable charge | Preserve exceptions/security signals and test alerting |
| 4 | Keep PostgreSQL opt-in, burstable/32 GiB/7 days for low-load dev; schedule when safe | Avoids always-on database overcapacity | Restore/RTO test and credit/latency monitoring |
| 5 | Rationalise duplicate GitHub jobs/builds and improve caches/concurrency | Reduces runner minutes and registry churn | Required branch/security gates unchanged |
| 6 | Add ACR lifecycle and orphaned disk/PVC/public-IP reviews | Removes slow storage/network leakage | Protect live digests, rollback window and backups |
| 7 | Add budgets, forecast alerts and mandatory allocation tags | Improves detection/accountability rather than directly reducing cost | Tested routing and named owners |
| 8 | Evaluate commitments only after stable production utilisation | May reduce steady compute rate | No commitment based on dev or short-lived demand |

## What not to optimise prematurely

Do not remove private PostgreSQL networking/TLS, probes, resource requests,
network policies, immutable image tags, security scans, tested backups or release
rollback capacity for small savings. Do not buy reservations before the workload
shape is stable. Do not move PostgreSQL into AKS, merge production and dev data,
replace managed identity with static credentials, or drop all logs merely to
reduce line items. Do not introduce multiple specialised pools, remote
Prometheus storage, geo-redundancy or a self-hosted runner fleet until a measured
availability, compliance or economic requirement supports the added complexity.

## Risks of over-aggressive cost cutting

Single-node and single-replica operation can turn upgrades, drains and node loss
into outages. Undersized nodes cause pending pods, throttling and OOM kills;
burstable database credit exhaustion causes latency spikes. Short backup
retention can make late-discovered corruption unrecoverable, while disabling HA
or geo protection can violate RTO/RPO. Hard telemetry caps and heavy sampling can
hide incidents or security evidence. Deleting apparently idle disks, PVCs,
public IPs or images can destroy data, break DNS/allowlists or remove rollback
paths. Over-narrow CI filters and cancelled security jobs can let defects ship.

Every saving should therefore have an owner, hypothesis, rollback, availability
and recovery impact, validation metric, and review date. Optimise unit economics
and idle time while preserving the platform's explicit security, recoverability
and production SLOs.
