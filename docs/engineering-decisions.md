# Engineering Decisions

## ADR-001: GitOps with Argo CD

**Status:** Accepted

**Context:** Kubernetes deployments require traceability, drift detection and repeatable rollback.

**Decision:** GitHub Actions builds and validates the image, pushes an immutable Git SHA tag and updates the Helm production tag in Git. Argo CD reconciles the cluster from Git.

**Alternatives:** Direct `kubectl apply`, direct `helm upgrade`, Flux CD.

**Consequences:** Git is the auditable source of truth and drift can self-heal, but Argo CD becomes an operational dependency.

## ADR-002: GitHub OIDC Instead of Client Secrets

**Status:** Accepted

**Context:** GitHub Actions needs Azure access without storing a long-lived password.

**Decision:** Use GitHub OIDC federation with Microsoft Entra ID.

**Alternatives:** Service-principal secret, publish profile, self-hosted runner identity.

**Consequences:** Tokens are short-lived and rotation overhead is reduced, but federated subjects and workflow permissions must match exactly.

## ADR-003: External Secrets for Runtime Secrets

**Status:** Accepted

**Context:** The Application Insights connection string must not be stored in Git or Helm values.

**Decision:** Store it in Azure Key Vault. External Secrets Operator uses Workload Identity and synchronises it to `flask-runtime-secrets`.

**Alternatives:** Manually created Secret, CSI volume mount, direct application Key Vault lookup.

**Consequences:** Key Vault remains authoritative and Git contains no secret value, but External Secrets becomes a runtime dependency and the value exists as a Kubernetes Secret.

## ADR-004: NGINX as the Public Entry Point

**Status:** Accepted, remediation required

**Decision:** Use NGINX Ingress with cert-manager and Let's Encrypt. The application backend Service should be `ClusterIP`.

**Current deviation:** Production still uses a Flask `LoadBalancer` Service, creating an additional public path.

**Consequences:** Centralised TLS and routing with lower public load-balancer use, but the ingress controller must be monitored and patched.

## ADR-005: Prometheus and Application Insights

**Status:** Accepted

**Decision:** Use Prometheus and Grafana for platform/application metrics, and OpenTelemetry plus Application Insights for requests, dependencies, exceptions and traces.

**Consequences:** Stronger coverage across Kubernetes and Azure-native diagnostics, with two telemetry pipelines to maintain.

## ADR-006: Immutable Git SHA Tags

**Status:** Accepted

**Decision:** Publish images using the full Git commit SHA and record the promoted SHA in production Helm values.

**Consequences:** Exact source-to-image traceability and deterministic rollback, with less human-readable tags and a need for registry lifecycle policies.
