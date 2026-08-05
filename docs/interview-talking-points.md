# Version 1 interview talking points

## A concise project narrative

“I took Traditional Strength from an application repository to a verified Azure production platform. Terraform manages the Azure estate, AKS separates system and application capacity, PostgreSQL is private, Key Vault secrets arrive through Workload Identity and External Secrets, GitHub Actions build and validate immutable releases, and Argo CD reconciles the Helm chart. The final application is healthy and Argo CD is Synced and Healthy. I also documented the one unresolved AKS encryption control as a quota-blocked, narrowly scoped risk.”

## Terraform state and imports

- There are two Terraform roots and remote states: `infra/` for shared resources/network/PostgreSQL and `infra/aks/` for AKS.
- The split limits change blast radius but introduces a coordination boundary; shared identifiers are supplied explicitly rather than coupling the states casually.
- Existing production resources were imported so Terraform could assume ownership without recreation.
- After PostgreSQL import, Azure's assigned zone appeared as drift that could provoke replacement. `ignore_changes = [zone]` records that service-owned behavior, while `prevent_destroy` protects the server.
- Terraform state contains the generated database password even though outputs do not. Backend access, plan artifacts, and logs therefore receive secret-level handling.
- A strong review answer: “Import does not prove convergence. I inspect refresh-only and normal plans, resource addresses, computed fields, replacements, and lifecycle guards before applying.”

## AKS production architecture

- `system` is the default System pool with critical-addons-only scheduling and host encryption.
- `production` is an autoscaling User pool labelled `workload=production`.
- `flask-app/values.yaml` supplies the matching `nodeSelector`; both the Deployment and Helm migration Job render it.
- This isolates business workload capacity from DNS, policy, and other cluster services.
- The production pool uses Azure Linux and ephemeral OS disks. Host encryption is deferred only because rotation required temporary regional vCPU capacity that Azure could not allocate.

Useful evidence:

```bash
kubectl get nodes -L agentpool,workload
kubectl get pods -n production -o wide
helm template flask-web-prod flask-app -n production \
  -f flask-app/values-production.yaml | rg -n 'nodeSelector|workload: production'
```

## GitOps with Argo CD

- `kubernetes/argocd/flask-web-production.yaml` tracks `main`, path `flask-app`, and production values.
- Automated sync uses pruning and self-healing and creates/labels the production namespace with Pod Security `restricted`.
- CI never treats ACR as desired state. It publishes an image and commits its immutable Git SHA tag; Argo CD renders and applies Git's declared state.
- This creates traceability from commit, to image, to values change, to live workload.

Troubleshooting sequence:

```bash
argocd app get flask-web-production
argocd app diff flask-web-production
kubectl describe application flask-web-production -n argocd
kubectl rollout status deployment/flask-web -n production
```

## Helm release design

- The release is `flask-web-prod`; `values-production.yaml` holds environment-specific configuration.
- The chart validates that image tags are immutable and rejects `latest`, `main`, `master`, or an invalid digest.
- A pre-install/pre-upgrade `flask db upgrade` Job has no retries and runs the selected application image.
- The Deployment has rolling-update controls, probes, a PDB, topology preferences, resource controls, hardened security contexts, and a `ClusterIP` Service behind NGINX ingress.
- Production stays at one replica with HPA off until PostgreSQL scale-out validation; `values-scale-out.yaml` is deliberately opt-in.
- An integration fix preserved the existing ingress name with `ingress.nameOverride`, preventing an unnecessary resource identity change.

## Private DNS and VNet peering

- PostgreSQL sits in a delegated subnet with public access disabled.
- The AKS cluster VNet and application VNet require both peering directions for predictable routing.
- The PostgreSQL private DNS zone is linked to both relevant VNets so CoreDNS can resolve the database FQDN to a private address.
- Terraform manages the peerings and links, with `prevent_destroy` on peering resources.
- Diagnosis separates name resolution from transport:

```bash
kubectl run dns-check -n production --rm -it --restart=Never \
  --image=busybox:1.36 -- nslookup <postgres-fqdn>
kubectl run tcp-check -n production --rm -it --restart=Never \
  --image=busybox:1.36 -- nc -vz <postgres-fqdn> 5432
```

Do not place credentials in these commands or print `DATABASE_URL`.

## PostgreSQL migration

- The production portal uses SQLAlchemy/Alembic migrations and PostgreSQL through `DATABASE_URL`.
- The database release was treated as a cutover: private connectivity and secret presence first, migration Job next, application rollout after success, then public health.
- A failed migration blocks the new rollout. Recovery begins with the retained Job and compatibility analysis; it does not blindly downgrade schemas.
- PostgreSQL automated backups provide a starting point, but Version 2 still needs recorded RPO/RTO and a tested point-in-time restore.

## Secrets management

- `kubernetes/external-secrets/azure-key-vault.yaml` defines the ServiceAccount, SecretStore, and ExternalSecret.
- Workload Identity exchanges a projected Kubernetes token for short-lived Azure access; no static Azure credential is required in the pod.
- External Secrets maps Key Vault values to `SECRET_KEY`, `DATABASE_URL`, and `APPLICATIONINSIGHTS_CONNECTION_STRING` in `flask-runtime-secrets`.
- The Deployment and migration Job consume keys using `secretKeyRef`.
- A real integration defect was fixed when `DATABASE_URL` had not been included in the ExternalSecret mapping.

Safe check:

```bash
kubectl get externalsecret flask-runtime-secrets -n production
kubectl get secret flask-runtime-secrets -n production \
  -o jsonpath='{.data.DATABASE_URL}' | grep -q .
```

## CI/CD quality gates

- Application CI validates Helm cutover/scale-out modes, runs Python tests, builds the container, blocks on High/Critical fixed vulnerabilities, publishes SHA tags only from `main`, promotes through Git, and validates rollout/health.
- Terraform CI runs formatting, backend-free validation, and gating Checkov before production-environment plan/apply jobs.
- Platform Security renders Helm, scans repository vulnerabilities/secrets/misconfiguration with Trivy, rejects tracked KeePass files, and produces an SBOM.
- CodeQL runs extended Python security queries; Playwright runs browser release flows; PostgreSQL, toolchain, dependency, and release workflows cover their own boundaries.
- Workflows are path-scoped, so a documentation-only PR may show only repository-required checks rather than every workflow.

## Checkov exceptions and risk management

- Exceptions are placed on the exact Terraform resource and identify the control and rationale.
- `CKV_AZURE_227` is not dismissed as a false positive: remediation was attempted and failed because Azure could not allocate the rotation node.
- [production-backlog.md](production-backlog.md) provides removal criteria, keeping the exception reviewable and temporary.
- Other exceptions describe architectural or cost decisions such as delegated-subnet PostgreSQL networking versus a Private Endpoint. The interview distinction is accepted design risk versus an external blocker.

## Azure quota constraints

- Host encryption on an existing node pool triggers rotation and needs temporary capacity beyond steady state.
- East US 2 had no regional vCPU headroom for the required two-vCPU temporary node.
- The safe response was to preserve a working production pool, record the failed remediation, request/increase quota, review a zero-destroy/zero-replacement plan, then retry and remove the exception.
- Lesson: deployment, upgrade, and rotation surge capacity belongs in quota planning.

## Repository-specific troubleshooting examples

### Argo CD is OutOfSync

Compare the Application against Git, confirm the target revision and production values, then inspect Helm rendering. Avoid editing live resources because self-heal will reverse the change.

### Migration Job fails

```bash
kubectl get jobs -n production
kubectl describe job -n production <migration-job>
kubectl logs -n production job/<migration-job> --all-containers --tail=200
```

Confirm image identity, secret key presence, DNS resolution, TCP 5432, and migration compatibility without exposing environment values.

### Pod stays Pending

Inspect events, node labels, taints, and production-pool capacity. In this repository, `workload=production` means the pod must not silently fall back to the System pool.

### Database hostname does not resolve

Check the private-zone VNet links and both peerings before changing application code. The historical fix was infrastructure/DNS integration, not a Flask defect.

### Health fails while Argo CD is healthy

Argo health is Kubernetes-resource health, not full user-path verification. Inspect ingress, TLS, Service endpoints, pod readiness, and application logs, then call the public endpoint again.

```bash
kubectl get ingress,service,endpoints -n production
kubectl get pods -n production
curl --fail --silent --show-error https://traditionalstrength.co.uk/health
```
