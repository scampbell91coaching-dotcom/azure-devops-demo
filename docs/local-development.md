# Local development

The root `Makefile` is the supported entry point for local checks. Run `make
help` to see every command. These commands do not deploy, run Terraform apply,
contact Kubernetes or Azure, or print configured database URLs.

## Prerequisites

- GNU Make and Git
- Python 3.12 or newer
- Node.js 20 or newer and npm
- Helm 3
- Terraform (used only for `fmt -check` by the release gate)
- PostgreSQL on loopback only, if running PostgreSQL integration tests
- ShellCheck is recommended; `make lint` uses it when available

Create the Python environment and install browser dependencies:

```bash
python3 -m venv platform-portal/.venv
platform-portal/.venv/bin/pip install -r app/requirements-dev.txt
platform-portal/.venv/bin/pip install -r platform-portal/requirements.txt
platform-portal/.venv/bin/pip install ruff
npm ci
npx playwright install chromium
make setup-check
```

## Commands

```bash
make setup-check    # verify tools and installed dependencies
make lint           # Ruff lint + format check, then optional ShellCheck
make test           # root, portal, release-helper, and developer-helper tests
make playwright     # disposable SQLite database and local browser server
make helm-validate  # helm lint/template only; never helm install/upgrade
make db-reset       # dedicated loopback PostgreSQL test database only
make release-gate   # existing release-evidence checks and sanitized reports
```

To inspect the current migration heads without configuring a production secret,
run Flask with an explicit, process-local validation secret:

```bash
cd platform-portal
SECRET_KEY='local-migration-validation-only' .venv/bin/flask --app portal:create_app db heads
```

This value is suitable only for local metadata inspection. The application has
no default production secret and still refuses normal startup when `SECRET_KEY`
is absent.

`make release-gate` intentionally fails on a dirty worktree and writes ignored,
sanitized reports under `evidence/release/`. It reuses
`scripts/release/release-evidence`; PostgreSQL checks remain optional unless
`POSTGRES_TEST_DATABASE_URL` is configured.

## Local PostgreSQL tests

Create a local PostgreSQL role that can create databases, then configure the
dedicated test URL in your shell. Do not commit it to a file:

```bash
export POSTGRES_TEST_DATABASE_URL='postgresql://ts_app:<password>@127.0.0.1:5432/traditional_strength_test'
make db-reset
```

The reset command validates the URL before connecting. It accepts only
`localhost`, `127.0.0.1`, or `::1`, and only the database name
`traditional_strength_test`. It connects through the same local server's
`postgres` maintenance database, terminates connections to the test database,
then drops and recreates it. The URL and password are never echoed. After the
reset, run the PostgreSQL tests through `make release-gate` or directly with the
configured environment variable.

## Common failures

- **Setup reports missing Python dependencies:** ensure
  `platform-portal/.venv` exists and install both requirements files shown above.
- **Playwright cannot find Chromium:** run `npx playwright install chromium`.
- **Port 8091 is busy:** stop the local process using it. The wrapper deliberately
  ignores `E2E_BASE_URL` so browser tests cannot be redirected to a remote site.
- **Database reset is refused:** check that the URL host is loopback, its database
  name is exactly `traditional_strength_test`, and its role can create databases.
- **Helm validation fails:** run `helm lint` on the named chart; the helper hides
  rendered manifests so secret-shaped chart values are not written to output.
- **Release gate says the worktree is dirty:** commit or intentionally stash local
  work before producing final evidence. No cleanup is performed automatically.
- **ShellCheck is skipped:** install ShellCheck and rerun `make lint`; its absence
  does not hide the Ruff results.
