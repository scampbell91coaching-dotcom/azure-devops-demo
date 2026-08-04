# Azure metadata inventory

The inventory CLI records safe metadata for the Azure CLI's active subscription. It collects resource groups, AKS clusters, ACR registries, PostgreSQL Flexible Servers and legacy Single Servers, Key Vaults, user-assigned managed identities, public and private DNS zones, public IP resources, and virtual networks.

## Prerequisites and usage

Install Azure CLI and authenticate with an identity that has read access to the intended subscription. Confirm the active context before collection:

```bash
az account show --query '{name:name,id:id,state:state}' --output table
scripts/platform/azure-inventory
```

The default output follows the repository evidence convention at `evidence/azure-inventory/`. It contains `azure-inventory.json`, `azure-inventory.md`, and the canonical `azure-secret-name-inventory.json` contract projection. Only that generated directory is ignored by Git. Select another local destination with `--output-dir`; do not choose a tracked directory or commit live output.

The directory is forced to mode `0700` and reports to `0600`; report replacement is atomic. Use `--require-complete` in automation to return exit code 2 when either resource collection or secret-name coverage is not complete. Reports are still written for diagnosis.

## Behaviour and security boundary

The collector runs only `az account show`, `az group list`, and `az resource list` with explicit metadata projections. It makes no Azure or Kubernetes writes and never calls credential, connection-string, key, secret, token, login-token, or kubeconfig APIs. It does not inspect Key Vault secrets, ACR credentials, PostgreSQL connection details, AKS credentials, resource properties, tags, or Kubernetes objects.

There is currently no approved Key Vault secret-name collector. Each discovered vault is explicitly represented as `coverage: "unsupported"` with an empty name list; discovery failure is `unknown`. Neither state is evidence that a secret is missing. The shared contract uses the exact string `schema_version: "1.0"` and five explicit scope fields.

Resource IDs contain subscription IDs and reports contain tenant, subscription, resource, and resource-group names. Treat that operational metadata as internal even though it contains no intended secret values. A defensive sanitiser removes sensitive keys from successful metadata. Raw Azure CLI stderr is used only in memory to select a bounded error category and is never persisted or printed.

The active subscription lookup is required and fails the command if Azure CLI is missing, authentication is unavailable, or the context cannot be read. Individual resource collections are best effort. Provider-registration and permission failures produce a `partial` report with categorical issues; an empty successful collection remains distinguishable from a failed collection through that issues list. By default a successfully written partial report exits zero so available evidence is retained; `--require-complete` makes incompleteness machine-readable through exit code 2.

Run the focused tests without contacting Azure:

```bash
python3 -m unittest discover -s scripts/platform/tests -p 'test_azure_inventory.py' -v
```
