# Release evidence CLI

Run the local, read-only release gate from any directory:

```sh
scripts/release/release-evidence --repo-root "$(pwd)"
```

The command prints a summary and writes `evidence/release/release-evidence.json`
and `evidence/release/release-report.md`. Use `--output-dir` to select another
location. Use repeated `--expected-document PATH` arguments to replace the
default document list.

The checks are worktree cleanliness, Ruff lint, Ruff formatting, pytest, exactly
one Alembic head, PostgreSQL tests, Helm rendering, Terraform formatting, merge
markers, and expected release documents. PostgreSQL tests are optional and reported as skipped unless
`POSTGRES_TEST_DATABASE_URL` is set. All other checks are mandatory; missing
tools fail closed.

The command only reads the repository and writes its two reports. It does not
write through Git, deploy, apply Terraform, or contact a Kubernetes cluster.
Command output is size-limited and common credential forms are redacted. Do not
put secrets in path names or custom document arguments.

Exit codes are `0` for ready, `1` for completed but not ready, and `2` for a
usage, repository, or report-writing error. `argparse` also uses `2` for invalid
arguments.

Development checks:

```sh
python3 -m unittest discover -s scripts/release/tests -v
shellcheck scripts/release/release-evidence  # when ShellCheck is installed
```

## CI parity and evidence boundaries

The command is a local repository gate, not a substitute for all GitHub Actions
jobs or deployment evidence. In particular:

- it runs the portal suite from `platform-portal/` with
  `POSTGRES_TEST_DATABASE_URL` unset; this is intentionally different from a
  root `pytest` invocation, which also discovers repository-level suites and
  requires their own environment;
- it verifies that the sole Alembic head is exactly
  `0023_organisation_invitation_delivery`;
- PostgreSQL coverage is optional locally and requires both
  `POSTGRES_TEST_DATABASE_URL` and a reachable, disposable local PostgreSQL
  service with the reset command's local roles and passwordless `sudo` access;
- Playwright is a separate gate. Run `npm ci`,
  `npx playwright install --with-deps chromium`, then
  `E2E_TEST_ONLY=1 npm run e2e`. The guard refuses a remote base URL;
- GitHub Actions uses the exact version in `.python-version`. Check the active
  interpreter with `python --version`; an already-created venv is not changed
  merely by editing `.python-version`;
- the JSON records the candidate Git commit and generation time. It does not
  query ACR, Argo CD, Kubernetes, or a live endpoint, so it cannot prove an
  image digest, deployed revision, or deployment freshness. Record those in
  the beta release acceptance record from the protected deployment workflow;
- pull-request validation needs no cloud secrets. Main-branch publish/verify
  jobs require the configured Azure OIDC variables
  `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
  `AKS_RESOURCE_GROUP`, and `AKS_CLUSTER_NAME`. Terraform workflows currently
  use same-named GitHub secrets; scheduled Renovate uses `RENOVATE_TOKEN`.

See [the detailed parity audit](../../docs/release/ci-parity-report.md) for the
command matrix and known gaps.
