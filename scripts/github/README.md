# GitHub metadata inventory

`github-inventory` creates a local, sanitized snapshot of repository metadata. It
uses only read-only `gh` commands and targets the repository associated with the
current working directory by default.

## Prerequisites

- Python 3.10 or newer.
- [GitHub CLI](https://cli.github.com/) installed and authenticated (`gh auth login`).
- Read access to the target repository. Environment and branch-protection data
  may require additional repository permissions; those areas are reported as
  `unauthorized` instead of failing the entire inventory.

## Usage

Run from the repository root:

```bash
scripts/github/github-inventory
```

To inspect another repository explicitly or choose a different local output:

```bash
scripts/github/github-inventory --repo OWNER/REPO --output-dir /tmp/github-inventory
```

The default reports follow the repository's evidence convention and are written
under `evidence/github-inventory/`. That exact generated directory is ignored by
Git; unrelated evidence remains visible. The directory is forced to mode `0700`
and each report to `0600`, including when the caller uses umask `022`. Reports
are written through an atomic temporary-file replacement.

- `github-inventory.json`: richer GitHub metadata for operators;
- `github-inventory.md`: human-readable summary; and
- `github-secret-name-inventory.json`: strict shared secret-name contract for
  the credential-audit consumer.

The shared artifact uses schema version string `"1.0"`. Each `secret_scopes`
entry explicitly contains `repository`, `environment`, `subscription`,
`resource_group`, and `key_vault`. GitHub repository secrets use the canonical
scope with the exact `OWNER/REPO` and a null environment. Environment secrets
use the same repository plus the exact environment name; Azure scope fields are
null. Coverage is `complete` only after successful name enumeration and
`unknown` after authorization or collection failure. No values or timestamps
are included in this contract artifact.

## Status semantics

Each collection area reports one of:

- `ok`: metadata was returned;
- `empty`: the request succeeded but no items exist (or the default branch has
  no protection rule);
- `unauthenticated`: GitHub CLI authentication is missing or invalid;
- `unauthorized`: authentication works but the identity lacks permission; or
- `unavailable`: the CLI/API failed or returned unusable data for another reason.

## Security boundaries

The collector invokes `gh auth status`, `gh repo view`, and `gh api` with GET
only. It does not perform GitHub writes. Repository and environment secret APIs
return names and timestamps, not values. Repository variable API responses can
contain values, so the parser explicitly retains only each variable's name and
timestamps. Every output object is also recursively filtered for sensitive field
names before writing. The generic recursive sanitizer treats every key named
`secrets` as sensitive by default; only the two known name-only paths in the
native inventory have a schema-specific exception. The shared projection is
then rebuilt from allowlisted `name` fields. Raw stdout and stderr are never
included in reports.

Review JSON before sharing it: repository names, URLs, workflow paths, variable
names, secret names, environment names, and protection configuration are not
secret values but may still be operationally sensitive.

## Tests

```bash
python3 -m pytest -q scripts/github/tests
```

Tests mock subprocess execution; they do not contact GitHub.

The producer-owned contract fixture is
`scripts/github/tests/fixtures/github-secret-name-inventory.v1.json`; consumers
should load that file unchanged in cross-tool contract tests.
