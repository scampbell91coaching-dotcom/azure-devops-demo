# Security architecture

## Scope

This is a repository-only control description. A manifest is evidence of
declared intent, not proof that the control is effective in a live cluster.
Secret values, tenant IDs, client IDs and subscription identifiers are omitted.

## Trust boundaries

| Boundary | Declared controls | Qualification |
| --- | --- | --- |
| Internet to application | HTTPS NGINX Ingress, cert-manager annotations, HSTS and browser-security annotations | NGINX is publicly reachable; no WAF or private origin is declared |
| Private portal edge | NGINX external authentication to OAuth2 Proxy using Entra OIDC | OAuth client and cookie secrets are an out-of-band Kubernetes Secret; Flask authorization remains a separate control |
| GitHub Actions to Azure | GitHub OIDC and `id-token: write`; environment-scoped release/apply jobs | Federated credentials and GitHub environment rules are external configuration |
| AKS workload to Key Vault | AKS OIDC, Workload Identity ServiceAccount and External Secrets `SecretStore` | Federated identity and Key Vault data-plane role are not managed by repository Terraform |
| Pod to PostgreSQL | Private DNS, VNet peering, TLS, NetworkPolicy CIDR/port allow rule | PostgreSQL grants for runtime versus migration users are not declared here |
| AKS to ACR | Kubelet identity receives `AcrPull`; immutable production tag | ACR is public Basic tier; image signing/admission verification is absent |

## Secret lifecycle

Azure Key Vault is authoritative for the application secret key, Application
Insights connection string, runtime database URL and migration database URL.
External Secrets refreshes the two application Kubernetes Secrets hourly and
owns them through `creationPolicy: Owner`. Application containers use
`secretKeyRef`; no secret value is passed in Helm values.

The Key Vault is looked up as an existing resource by Terraform, rather than
created in this repository. Terraform's PostgreSQL module also writes generated
server metadata and the administrator password to that vault. The generated
password is present in remote Terraform state because Azure requires it during
creation; state and binary plan access are therefore sensitive.

The OAuth2 Proxy Secret is explicitly excluded from Git and is not managed by
External Secrets in the current manifests. That is an operational dependency
and a lifecycle gap, not a repository-managed secret path.

### Runtime and migration database identities

The application Deployment and private portal read the runtime URL. The Helm
migration Job and Argo CD PreSync Job read the migration URL. This prevents the
migration connection string from being attached to long-lived web pods.
However, the repository does not declare the database users or grants behind
those URLs. Technical reviewers should treat credential separation as
implemented and database privilege separation as unverified/external.

## Kubernetes controls

- Argo CD applies Pod Security Admission labels at `restricted` level to the
  production namespace it creates.
- Web and migration containers run as non-root, use RuntimeDefault seccomp,
  drop all Linux capabilities, disable privilege escalation and use a read-only
  root filesystem with writable `emptyDir` mounts.
- Application pods disable automatic ServiceAccount token mounting.
- Resource requests and limits, probes, rolling-update settings and a PDB are
  declared for the Helm release.
- The Helm chart starts with default-deny ingress and egress, then allows DNS,
  HTTPS, ingress-controller traffic and database traffic to the private CIDR.
- Private-platform NetworkPolicies restrict ingress to OAuth2 Proxy and the
  portal, but do not declare default-deny or egress policies for those pods.
  Their egress is therefore not equivalently constrained by these manifests.
- Azure network policy and Azure Policy are enabled on AKS. The repository does
  not include specific Azure Policy assignments or admission policies beyond
  Pod Security labels.

## Supply-chain and CI controls

GitHub Actions are pinned to commit SHAs. Application workflows run tests,
render manifests, build images and block on fixed-version Trivy HIGH/CRITICAL
findings (with unfixed vulnerabilities ignored in the blocking scan). The
platform-security workflow performs filesystem vulnerability, secret and IaC
scanning and emits an SPDX JSON SBOM. Terraform uses format, validate and
Checkov gates. CodeQL and Dependabot configuration are also present.

Production desired state references full Git commit SHA tags, although the
public workflow additionally pushes mutable short-SHA and `latest` tags. The
production values never select `latest`. Images are not signed and the cluster
does not verify provenance or signatures.

## Identity paths

Two federation paths must not be conflated:

1. GitHub Actions exchanges a GitHub OIDC token for an Azure token to publish
   images, plan/apply Terraform and invoke AKS checks.
2. External Secrets uses an AKS-issued ServiceAccount token and an Entra
   federated credential to read Key Vault.

Neither path uses a committed client secret. OAuth2 Proxy is different: its OIDC
client secret and cookie secret are Kubernetes Secret values maintained outside
the current External Secrets mapping.

## Evidenced gaps

- public AKS API and public ACR endpoint;
- no WAF, private origin or DDoS design declared beyond Azure defaults;
- AKS local-account disablement and Entra cluster integration are deferred;
- host encryption absent on the production User pool;
- raw private-platform workloads lack the Helm workload node selector and
  comprehensive default-deny/egress policies;
- identity federation and Key Vault grants are not fully represented as IaC;
- no automated application, OAuth or database credential rotation;
- no image signature/provenance enforcement;
- no repository evidence of tenant isolation, privacy retention policy or
  audited SaaS authorization boundaries.

See [AKS deferred controls](security/aks-deferred-controls.md), [identity audit](security/identity-and-runtime-audit.md) and [limitations](limitations.md).
