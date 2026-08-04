# Credential coverage audit

This read-only tool compares a user-maintained credential metadata manifest with optional metadata-only GitHub Actions and Azure Key Vault inventories. It writes JSON and Markdown coverage reports without obtaining, decoding, or accepting credential values.

## Security boundary

The tool does not open KeePass databases, invoke KeePass, GitHub, Azure, Terraform, Kubernetes, SSH, DNS, or PostgreSQL commands, or infer credential existence from infrastructure resources. No approved metadata-only KeePass export mechanism exists in this repository, so KeePass group structure must be reviewed manually and represented only through the manifest fields allowed by the versioned [schema](credential-metadata.schema.json). Never export KeePass entries or values for this tool.

Inputs are strict allowlists. A manifest entry contains only `name`, `owner`, `last_verified`, `storage_location`, and `rotation_status`. Inventory entries contain only names and non-sensitive scope labels. Common value-bearing fields are rejected before parsing, errors do not include input contents, and output is reconstructed from allowed metadata fields. Treat names and ownership metadata as potentially sensitive operational information and do not commit real manifests or reports.

Cloud resources, workflows, Terraform declarations, ExternalSecrets, and documentation express an expectation only. An item is `present` solely when its exact canonical storage label occurs in a supplied metadata inventory. It is `missing` only when the relevant inventory was supplied and the label is absent. Otherwise it is `unknown`.

## Prerequisites and usage

Python 3.12 or newer is the only prerequisite. Start from the fake [example manifest](examples/credential-metadata.example.json) and keep the real copy outside Git.

Storage labels use one of these exact canonical forms:

- `github-actions:repository:<NAME>` for repository Actions secrets.
- `github-actions:environment:<ENCODED_ENVIRONMENT>:<NAME>` for environment Actions secrets. Percent-encode the exact UTF-8 environment name per RFC 3986; for example, `prod/eu` becomes `prod%2Feu`.
- `azure-key-vault:<SUBSCRIPTION_ID>:<RESOURCE_GROUP>:<KEY_VAULT>:<NAME>` for an exact Azure vault scope.
- Other labels (for KeePass, SSH, DNS, PostgreSQL, AKS, or local development) are permitted but remain `unknown`, because no approved inventory adapter verifies them.

`--github-inventory` consumes the unmodified Platform 1 producer projection:

```json
{"schema_version":"1.0","source":"github","generated_at":"2026-08-04T12:00:00Z","collection_status":"complete","secret_scopes":[{"scope":{"repository":"acme/widgets","environment":null,"subscription":null,"resource_group":null,"key_vault":null},"coverage":"complete","secret_names":["DEPLOY_TOKEN"]}]}
```

`--azure-inventory` consumes the unmodified Platform 2 projection. Platform 2 deliberately does not enumerate Key Vault secret names, so discovered vaults are `unsupported` and all matching credential coverage remains `unknown`:

```json
{"schema_version":"1.0","source":"azure","generated_at":"2026-08-04T12:00:00Z","collection_status":"partial","secret_scopes":[{"scope":{"repository":null,"environment":null,"subscription":"00000000-0000-0000-0000-000000000001","resource_group":"rg-production","key_vault":"kv-production"},"coverage":"unsupported","secret_names":[]}]}
```

Run the audit with files produced by a separately reviewed metadata-only process:

```bash
python3 scripts/credentials/credential_audit.py \
  --manifest /safe/path/credential-metadata.json \
  --github-inventory /safe/path/github-metadata.json \
  --azure-inventory /safe/path/azure-metadata.json \
  --output-dir evidence/credential-audit
```

Both inventory arguments are optional. `--as-of YYYY-MM-DD` makes review and tests reproducible; it defaults to the local current date. `--stale-days` defaults to 90. A verification date older than the threshold, or in the future, is `stale`. Rotation states `due` and `required` add `rotation-required`; these hygiene findings can coexist with any coverage state.

The default follows the repository evidence convention: `evidence/credential-audit/credential-audit.json` and `credential-audit.md`. The tool creates that directory at mode `0700` and atomically replaces reports at mode `0600`. The credential-audit evidence directory is ignored; do not commit real manifests or reports.

Run the focused tests:

```bash
python3 -m pytest -q scripts/credentials/tests
```
