# Version 1 architecture

## Scope and validated state

This document describes the implemented Traditional Strength Version 1 platform. The production Argo CD Application `flask-web-production` is Synced and Healthy, and the public `/health` endpoint is healthy. Disabled chart features and roadmap items are identified explicitly.

## End-to-end platform architecture

```mermaid
flowchart TB
    Client[Browser or API client]
    DNS[Public DNS]
    NGINX[NGINX ingress controller]
    Ingress[traditionalstrength.co.uk Ingress]
    Service[flask-app ClusterIP Service]
    Pods[Flask portal pods]
    Migration[Helm pre-upgrade migration Job]
    DB[(Azure PostgreSQL Flexible Server)]
    AI[Application Insights]
    LAW[Log Analytics and AKS insights]
    KV[Azure Key Vault]
    ESO[External Secrets Operator]
    Secret[Kubernetes runtime Secret]
    ACR[Azure Container Registry]
    Git[GitHub repository]
    Actions[GitHub Actions]
    Argo[Argo CD]

    Client --> DNS -->|HTTPS| NGINX --> Ingress --> Service --> Pods
    Pods -->|TLS over private network| DB
    Migration -->|schema upgrade| DB
    Pods --> AI
    Pods -. cluster telemetry .-> LAW
    KV --> ESO --> Secret
    Secret --> Pods
    Secret --> Migration
    Git --> Actions
    Actions --> ACR
    Actions -->|update immutable image tag| Git
    Git --> Argo -->|Helm reconciliation| Pods
    ACR -->|image pull| Pods
    ACR -->|same image| Migration
```

The application is exposed only through an ingress-backed `ClusterIP` Service. Production uses one application replica during PostgreSQL cutover; the scale-out overlay is not active.

## CI/CD and GitOps deployment flow

```mermaid
sequenceDiagram
    actor Developer
    participant GitHub
    participant CI as GitHub Actions
    participant ACR
    participant Argo as Argo CD
    participant Helm
    participant AKS
    participant Health as Public health endpoint

    Developer->>GitHub: Open pull request
    GitHub->>CI: Run path-scoped validation
    CI->>CI: Tests, Helm, Trivy, Checkov, CodeQL, browser and release gates
    Developer->>GitHub: Merge approved change to main
    GitHub->>CI: Run main release workflow
    CI->>ACR: Push immutable Git SHA image
    CI->>GitHub: Commit production image tag
    Argo->>GitHub: Poll desired state
    Argo->>Helm: Render flask-app values
    Helm->>AKS: Run migration hook
    AKS->>ACR: Pull selected image
    Helm->>AKS: Reconcile Deployment and services
    Argo->>AKS: Prune drift and self-heal
    CI->>Health: Verify HTTPS /health
```

Feature branches validate but do not publish or promote. GitHub OIDC supplies short-lived Azure authentication. Git contains desired state, ACR contains images, and Argo CD owns delivery to AKS.

## AKS system pool and production workload pool

```mermaid
flowchart TB
    subgraph Cluster[Azure Kubernetes Service]
        Scheduler[Kubernetes scheduler]

        subgraph SystemPool[system pool - System mode]
            CoreDNS[CoreDNS]
            KubeSystem[cluster-critical add-ons]
            Policy[Azure policy and agents]
        end

        subgraph ProductionPool[production pool - User mode]
            Label[workload=production]
            Web[Flask Deployment]
            Job[Database migration Job]
        end
    end

    Scheduler --> SystemPool
    Scheduler -->|nodeSelector workload=production| Web
    Scheduler -->|nodeSelector workload=production| Job
    Label --- Web
    Label --- Job
```

The system pool uses `only_critical_addons_enabled`, host encryption, an ephemeral OS disk, and Azure Linux. The autoscaling production User pool carries the workload label and also uses Azure Linux and an ephemeral OS disk. Host encryption on that pool is the sole quota-blocked hardening item documented in [production-backlog.md](production-backlog.md).

## AKS-to-PostgreSQL private networking and DNS

```mermaid
flowchart LR
    Pod[Flask pod]
    CoreDNS[AKS CoreDNS]
    PrivateZone[Private DNS zone<br/>postgres.database.azure.com]
    PrivateIP[PostgreSQL private address]
    DB[(Flexible Server<br/>public access disabled)]

    subgraph AKSVNet[AKS virtual network]
        Pod --> CoreDNS
    end

    subgraph AppVNet[Application virtual network]
        DBSubnet[Delegated database subnet]
        PrivateIP --> DB
        DBSubnet --- DB
    end

    AKSVNet <-->|bidirectional VNet peering| AppVNet
    CoreDNS -->|resolve server FQDN| PrivateZone
    PrivateZone -->|private A record| PrivateIP
    Pod -->|TCP 5432 and TLS| PrivateIP
```

Terraform manages both peering directions and links the private DNS zone to the application VNet and AKS VNet. The application connects by FQDN with TLS rather than by a fixed address. The server has public network access disabled and is protected from accidental Terraform destruction.

## Secret flow from Key Vault to Kubernetes

```mermaid
sequenceDiagram
    participant Admin as Approved secret owner
    participant KV as Azure Key Vault
    participant SA as external-secrets-kv ServiceAccount
    participant Entra as Microsoft Entra ID
    participant ESO as External Secrets Operator
    participant K8s as flask-runtime-secrets
    participant App as Flask pod or migration Job

    Admin->>KV: Store or rotate approved value
    ESO->>SA: Use projected workload token
    SA->>Entra: Exchange token via federated identity
    Entra-->>ESO: Short-lived Azure access token
    ESO->>KV: Read named secrets
    KV-->>ESO: Return values over TLS
    ESO->>K8s: Create or refresh Kubernetes Secret
    K8s-->>App: Inject keys through secretKeyRef
```

The `ExternalSecret` refreshes `SECRET_KEY`, `DATABASE_URL`, and `APPLICATIONINSIGHTS_CONNECTION_STRING`. Terraform state contains the generated PostgreSQL administrator password because Azure requires it for resource creation, so state access is a sensitive security boundary. Neither Helm nor Git stores the runtime values.

## Infrastructure ownership

| Concern | Source of truth |
| --- | --- |
| Shared Azure resources, network, PostgreSQL | `infra/` Terraform state and configuration |
| AKS and node pools | `infra/aks/` Terraform state and configuration |
| Application package | `flask-app/` Helm chart |
| Production image selection | `flask-app/values-production.yaml` |
| Kubernetes reconciliation | `kubernetes/argocd/flask-web-production.yaml` and Argo CD |
| Runtime secret values | Azure Key Vault |
| Secret synchronisation | `kubernetes/external-secrets/azure-key-vault.yaml` |
| Images | Azure Container Registry |

## Runtime controls

The chart implements rolling updates, a pre-deployment migration hook, startup/readiness/liveness probes, a Pod Disruption Budget, CPU and memory controls, topology preferences, non-root execution, dropped capabilities, RuntimeDefault seccomp, a read-only root filesystem, Pod Security `restricted`, and default-deny ingress/egress with explicit required paths.

Observability includes application health and metrics endpoints, Application Insights/Log Analytics infrastructure, Azure Monitor instrumentation, and runbooks. Prometheus Operator objects exist in the chart but are disabled in production pending live label and routing validation; screenshots are evidence of prior monitoring use, not proof that every proposed resource is currently active.

## Related documents

- [Azure networking architecture](networking.md)
- [Version 1 summary](version-1-summary.md)
- [Engineering decisions](engineering-decisions.md)
- [Azure PostgreSQL](azure-postgresql.md)
- [Operational runbook](runbook.md)
- [Roadmap](roadmap.md)
