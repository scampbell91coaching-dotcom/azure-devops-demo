# Identity and runtime security audit

Audit date: 2026-08-06. Scope: repository configuration only. No Azure or
Kubernetes API was queried, so statements about deployed resources are not live
attestation. Secret values were neither read nor copied.

## Current identity model

The `infra/aks` Terraform root declares `oidc_issuer_enabled = true` and
`workload_identity_enabled = true`. AKS itself uses a system-assigned identity;
its kubelet identity has only the repository-declared `AcrPull` assignment on
the existing registry. Kubernetes RBAC is enabled, but Microsoft Entra AKS
authentication is not declared and local accounts remain enabled under a
documented Checkov exception. No application workload calls the Kubernetes API.

External Secrets Operator (ESO) is the only declared workload-identity
consumer. The namespace-scoped `external-secrets-kv` ServiceAccount is annotated
with fixed client and tenant IDs. The `SecretStore` explicitly names that
ServiceAccount and uses `WorkloadIdentity`. ESO requests a short-lived,
audience-scoped token for this account and exchanges it at the cluster OIDC
issuer. `automountServiceAccountToken: false` prevents an unrelated default API
token mount; it does not prevent the TokenRequest flow used by ESO.

The repository does **not** declare or import the user-assigned managed identity,
its federated identity credential, or its Key Vault role assignment. Therefore
the subject, issuer, audience, identity ownership, and effective Azure rights
cannot be verified from code. The expected federation subject is
`system:serviceaccount:production:external-secrets-kv`, with audience
`api://AzureADTokenExchange`. The `azure.workload.identity/use: "true"` pod label
is required when the Azure Workload Identity mutating webhook injects credentials
directly into an application pod. This design instead has ESO request a token
for `serviceAccountRef`; adding that label to application pods would be
incorrect, and the installed ESO/controller configuration must be verified live.

## Key Vault and secret flow

`stevedevopskv30841` is referenced as an existing vault. Terraform reads the
vault and writes PostgreSQL material when that optional module is enabled, but
does not declare the vault's `enable_rbac_authorization` setting. The only root
role assignment is conditional `Key Vault Secrets User` for a Terraform CI
principal. No Owner, Contributor, or Key Vault Administrator grant is declared.

The ESO identity's data-plane permission is absent from Terraform. Live review
must confirm the vault uses Azure RBAC (or identify an existing access policy)
and that this identity has only `Key Vault Secrets User`, preferably scoped to
the vault dedicated to this workload. Azure's built-in role is vault-wide; if
unrelated secrets share the vault, use separate vaults or a supported narrower
architecture rather than assuming the `ExternalSecret.data` list is an Azure
authorization boundary.

The namespace `SecretStore` prevents cross-namespace references. Every hour ESO
reads three named entries and owns the `flask-runtime-secrets` Kubernetes Secret:
`flask-secret-key`, `database-url`, and
`applicationinsights-connection-string`. Application pods consume keys through
`secretKeyRef`; values are not present in Helm values. `creationPolicy: Owner`
means deleting the ExternalSecret can garbage-collect the generated Secret.
Existing pods keep environment values until restart, failed refreshes leave the
last successfully synchronized Secret in place, initial synchronization failure
prevents pods that require missing keys from starting, and rotation does not
update environment variables in already-running pods. Alert on ExternalSecret
NotReady and restart/redeploy consumers after an approved rotation.

## Service accounts and Kubernetes RBAC

Application, migration, lead-magnet, private portal, OAuth proxy, and Redis pods
all set `automountServiceAccountToken: false`. They use the namespace default
ServiceAccount but receive no token, and the repository declares no Role,
RoleBinding, ClusterRole, or ClusterRoleBinding for them. Dedicated application
ServiceAccounts would add names without creating a privilege boundary while no
API permissions exist. Add a dedicated account and namespace Role only if a
future feature has a concrete Kubernetes API requirement.

The Argo CD Application uses the `default` AppProject and reconciles the
production namespace. Argo CD and CI cluster permissions are not declared here,
so cluster-admin assumptions cannot be excluded. Inventory their live bindings
and constrain the AppProject destination/resource allow-list and deployment
identity to the production namespace where operationally compatible.

## Runtime privilege boundary

The raw Flask manifest and both application charts declare non-root execution,
fixed UID/GID values, `allowPrivilegeEscalation: false`, `capabilities.drop:
[ALL]`, RuntimeDefault seccomp, and CPU/memory requests and limits. Production
Flask and lead-magnets use read-only root filesystems with explicit `/tmp`
`emptyDir` volumes; Flask also mounts writable `/app/data`, and lead-magnets
mounts its data PVC. The private portal and OAuth proxy have the same core
controls; the portal has explicit writable data and temporary mounts. Redis is
similarly constrained. The production namespace is labelled for the Restricted
Pod Security Standard through Argo CD. These existing read-only configurations
are supported by explicit writable mounts, but only runtime tests can prove every
code path is compatible.

One operational caveat: the private portal init container has a read-only root
filesystem but no `/tmp` mount. Add one only if observed migration tooling needs
it; the repository does not establish that compatibility requirement.

## PostgreSQL privilege separation

Current production configuration reuses `flask-runtime-secrets/DATABASE_URL` for
the Flask Deployment, its migration Job, and the private portal's migration init
container. Terraform creates only the Flexible Server administrator login and
stores its credentials. The AzureRM provider does not create PostgreSQL roles or
grants, so inventing a runtime role in Terraform would not provision it safely.

The Helm chart now has separate `migration.secretName` and
`migration.secretKey` settings. Their defaults deliberately retain the current
reference and avoid an outage. Complete separation in a maintenance window:

1. Connect over the private network as the database owner using an approved
   client; create a login role for runtime, grant CONNECT and USAGE, and grant
   only the table/sequence/function privileges the application demonstrably
   needs. Configure default privileges for objects created by the migration
   owner. Keep schema ownership and DDL rights with the migration identity.
2. Test migrations as the owner and application behavior as the restricted role,
   including future Alembic-created objects and rollback. Do not log either URI.
3. Store distinct complete TLS URLs as separate Key Vault secrets. Extend ESO to
   create distinct Kubernetes Secret keys (or Secrets), retaining namespace
   ownership and the same least-privilege reader identity.
4. Change `database.secretName/secretKey` to the runtime credential and
   `migration.secretName/secretKey` to the owner credential. Update the private
   portal init container separately or remove migration duties from that
   Deployment. Render, validate, deploy through GitOps, and verify before revoking
   the old administrator URL.

## GitHub OIDC

Azure login steps use `azure/login` with client, tenant, and subscription IDs;
no Azure client secret is referenced. Jobs that log in have job-scoped
`id-token: write`. IDs are inconsistently stored as GitHub `vars` and `secrets`;
they are identifiers, not credentials, so variables are preferable, but changing
workflow ownership is outside this audit. Production apply/verification jobs use
the `production` environment, while several image-publish and plan jobs do not.
The repository cannot verify federated credential subjects or Azure role
assignments. Live review must ensure PR subjects cannot authenticate, environment
subjects protect production, and build/publish, Terraform plan/apply, and AKS
verification use separate identities where practical. The general Terraform
workflow can apply on `main`; its principal therefore warrants particularly
tight scope and environment approval.

## Secret findings and remaining risks

No literal production secret was found in tracked manifests or application
configuration. Test-only keys and local example placeholders are clearly scoped.
OAuth2 Proxy still requires a long-lived Entra application client secret from a
Kubernetes Secret; this is end-user OIDC authentication, not GitHub Azure login.
Its delivery mechanism is not declared as an ExternalSecret, and the private
platform README describes manual Secret prerequisites. Consolidate those values
into the existing ESO/Key Vault system rather than creating a second mechanism.

Terraform state contains the generated PostgreSQL administrator password, and
saved plans can contain it. The backend/state identity and storage RBAC remain a
sensitive boundary. The committed environment files contain Azure resource and
principal identifiers but no secret values. Application Insights connection
string output is marked sensitive; PostgreSQL outputs expose names and metadata
only.

## Live verification required

- Confirm AKS reports OIDC and workload identity enabled and record the issuer.
- Inspect the managed identity and federated credential issuer, subject, and
  audience; compare the client ID with the ServiceAccount annotation.
- Inspect the vault authorization model and all effective role assignments or
  access policies without reading secret values.
- Verify ESO version/configuration supports ServiceAccount TokenRequest auth,
  and inspect SecretStore/ExternalSecret Ready conditions and alerts.
- Inventory Kubernetes RBAC for Argo CD, CI, operators, ESO, and default accounts.
- Inventory GitHub environment protection, federated subjects, and Azure roles.
- Exercise read-only filesystem paths and the two database identities before
  changing production references.
