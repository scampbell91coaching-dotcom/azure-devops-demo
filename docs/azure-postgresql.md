# Azure PostgreSQL foundation

This foundation adds an opt-in Azure Database for PostgreSQL Flexible Server for Traditional Strength. It is disabled by default and is not enabled in the tracked development environment. It creates no production resources unless a future, separately reviewed production configuration explicitly opts in.

## Architecture and defaults

The root Terraform stack calls the reusable `infra/modules/postgresql` module. The server uses the existing `eastus2` resource group and `vnet-devops-lab` conventions:

- private access only; public network access is disabled;
- the existing `snet-database` subnet is delegated only when PostgreSQL is enabled;
- a private DNS zone ending in `postgres.database.azure.com` is linked to the VNet;
- TLS is enforced by `require_secure_transport`, with TLS 1.2 as the explicit minimum;
- clients are expected to use `sslmode=verify-full` and a trusted Microsoft certificate chain;
- PostgreSQL 16, 32 GiB storage with auto-grow, and the burstable `B_Standard_B1ms` SKU;
- seven days of automated point-in-time backups, without geo-redundancy;
- high availability is optional and disabled by default;
- a dedicated `traditional_strength` database; and
- a generated 32-character administrator password, stored with the host, port, database, and username in the existing Azure Key Vault.

The password is sensitive Terraform state data because Azure requires it during server creation. Remote state access must remain tightly restricted. Terraform never outputs the password. Saved binary plan files can also contain sensitive values, so the dedicated workflow neither saves nor uploads one. The non-secret `postgresql_connection` output exposes the hostname, port, database, TLS mode, and Key Vault secret names needed to configure AKS.

## Network prerequisite

The current AKS Terraform does not place its node pool in `vnet-devops-lab`. A private PostgreSQL server will therefore not be reachable from AKS until a separately reviewed networking change connects AKS to this VNet (for example, by using an AKS subnet in the VNet or supported peering and DNS forwarding). Do not enable PostgreSQL for an application rollout until private DNS resolution and TCP 5432 reachability have been demonstrated from a disposable pod.

This foundation deliberately does not change the live AKS network because moving an existing cluster can be disruptive.

## Provisioning safely

1. Copy the values from `infra/environments/dev/postgresql.tfvars.example` into an approved environment-specific variable file. Replace the placeholder server and Key Vault names. Do not add a password; Terraform generates it.
2. Confirm the executing identity can manage the database resources, private DNS, subnet delegation, and Key Vault secrets. It needs secret data-plane write access under the vault's current RBAC/access-policy model.
3. Run validation:

   ```bash
   terraform -chdir=infra fmt -check -recursive
   terraform -chdir=infra init -backend=false
   terraform -chdir=infra validate
   checkov --directory infra/modules/postgresql --framework terraform --compact --quiet
   ```

4. Run a development plan using the existing backend and reviewed values:

   ```bash
   terraform -chdir=infra init -backend-config=environments/dev/backend.hcl
   terraform -chdir=infra plan \
     -var-file=environments/dev/terraform.tfvars \
     -var-file=environments/dev/postgresql.tfvars \
     -no-color
   ```

5. Review subnet delegation, DNS, server, database, and Key Vault secret changes. This repository change does not authorize `terraform apply`. Applying requires the normal change approval outside this branch.

The `Azure PostgreSQL plan` GitHub Actions workflow runs formatting, validation, and a failing Checkov scan on pull requests. A manual dispatch accepts only the non-secret development server and Key Vault names, authenticates using the existing OIDC secrets, and prints a speculative plan without saving an artifact. It contains no apply job. The older general Terraform workflow can apply on `main`; keep `postgresql_enabled = false` in its tracked tfvars until that workflow is separately changed to an approved plan/apply gate.

Checkov exceptions are documented next to the affected resources. Geo-redundant backup is deliberately optional because it is region-dependent and increases cost (`CKV_AZURE_136`). Private Flexible Server networking uses Azure's delegated-subnet model rather than a Private Endpoint (`CKV2_AZURE_57`). Connection secrets do not receive arbitrary expiry dates (`CKV_AZURE_41`): expiring them without an automated rotation controller would break consumers. Password rotation must instead be scheduled, tested, and coordinated with Key Vault consumers.

## Connecting from AKS

The module writes server-scoped Key Vault secrets, avoiding collisions with existing or future servers. For a server named `<server>`, it creates:

| Key Vault secret | Purpose |
| --- | --- |
| `<server>-host` | Private Flexible Server FQDN |
| `<server>-port` | Port `5432` |
| `<server>-database` | Application database |
| `<server>-username` | Administrator login |
| `<server>-password` | Generated password |

Extend the existing `ExternalSecret` only after provisioning and network verification. Map the values into a Kubernetes Secret and build the connection URI inside the workload or chart; do not commit a URI containing the password. Use `sslmode=verify-full`. Example diagnostic connection from a private-network client:

```bash
PGSSLMODE=verify-full psql \
  --host="$POSTGRES_HOST" \
  --port=5432 \
  --username="$POSTGRES_USER" \
  --dbname="$POSTGRES_DB"
```

Retrieve credentials through the approved Key Vault/External Secrets path. Do not print them in CI logs, Terraform outputs, shell history, or Kubernetes manifests.

## Backups and recovery

Flexible Server takes managed automated backups and supports point-in-time restore within the configured seven-day retention period. Seven days is the conservative cost-conscious starting point; increase it up to 35 days when recovery objectives require it. Geo-redundant backup is off by default and must be enabled deliberately after checking regional support and cost.

Before relying on the service, document RPO/RTO and test a point-in-time restore into a new server. A restore creates a new server; it does not overwrite the source. Validate the restored database, application login, private DNS, and Key Vault rotation process before declaring the exercise successful.

Useful read-only operational checks (replace placeholders; these do not reveal secret values):

```bash
az postgres flexible-server show --resource-group <resource-group> --name <server> --output table
az postgres flexible-server backup list --resource-group <resource-group> --name <server> --output table
az keyvault secret list --vault-name <vault> --query "[?starts_with(name, '<server>-')].{name:name,enabled:attributes.enabled}" --output table
```

A point-in-time recovery creates a new server. Review the generated name, timestamp, networking, DNS, and cost before running an approved restore:

```bash
az postgres flexible-server restore \
  --resource-group <resource-group> \
  --name <restored-server> \
  --source-server <source-server> \
  --restore-time <UTC-RFC3339-timestamp>
```

## High availability

Set `postgresql_high_availability_enabled = true` only after verifying SKU and regional zone support. `ZoneRedundant` is the default HA mode when enabled; `SameZone` is also accepted. HA adds a standby and materially increases cost. Burstable SKUs may not support the chosen HA mode, so select an eligible General Purpose SKU in the same reviewed change.

## Deletion

Deletion is destructive and is never automated by the PostgreSQL workflow. The server has Terraform `prevent_destroy` protection, so removal requires a separate, explicit code review that removes the guard; do not bypass it with state manipulation. Before removal:

1. confirm application traffic has moved and no workload still references the five Key Vault secrets;
2. take and verify any required logical export or long-term retention copy outside the server lifecycle;
3. record the final restore deadline implied by backup retention;
4. review a destroy plan scoped through the normal environment configuration, not `-target`; and
5. obtain explicit environment-owner approval.

After the server is destroyed, automated backups are not a substitute for an independently verified export. Remove stale External Secret mappings only in a separate application/configuration change. Key Vault soft-delete may retain deleted secret versions according to the vault policy; never purge them as part of routine Terraform deletion.
