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

## ADR-003: External Secrets for Runtime and Migration Secrets

**Status:** Accepted

**Context:** Application and database credentials must not be stored in Git or Helm values, and schema credentials should not be attached to long-lived pods.

**Decision:** Store values in Azure Key Vault. External Secrets Operator uses Workload Identity and synchronises separate `flask-runtime-secrets` and `flask-migration-secrets` targets.

**Alternatives:** Manually created Secret, CSI volume mount, direct application Key Vault lookup.

**Consequences:** Key Vault remains authoritative and Git contains no secret value, but External Secrets becomes a runtime dependency and the value exists as a Kubernetes Secret.

## ADR-004: NGINX as the Public Entry Point

**Status:** Accepted

**Decision:** Use NGINX Ingress with cert-manager and Let's Encrypt. The application backend Service should be `ClusterIP`.

**Consequences:** Centralised TLS and routing with lower public load-balancer use, but the ingress controller must be monitored and patched.

## ADR-005: Observability Resources Remain Opt-in Until End-to-End Wiring Exists

**Status:** Accepted

**Decision:** Keep the Prometheus `ServiceMonitor`, alert rules and Grafana dashboard disabled in production until the deployed portal exposes metrics and scrape, storage, notification and ownership paths are validated. Keep Application Insights classified as a resource foundation until the production application is instrumented.

**Consequences:** The repository avoids claiming a non-functional monitoring path, but current observability is limited to shallow health, logs and Azure resource foundations.

## ADR-006: Immutable Git SHA Tags

**Status:** Accepted

**Decision:** Publish images using the full Git commit SHA and record the promoted SHA in production Helm values.

**Consequences:** Exact source-to-image traceability and deterministic rollback, with less human-readable tags and a need for registry lifecycle policies.
