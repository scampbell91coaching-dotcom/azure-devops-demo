# Release evidence and CI parity

Audited against the integrated POWERLIFTING branch on 2026-08-13. This is a
repository-only assessment; no production, Azure, Argo CD, registry, or live
database calls were made.

## Release proof matrix

| Concern | Local release-evidence | GitHub Actions | Release interpretation |
|---|---|---|---|
| Candidate revision | Records `git rev-parse HEAD` and fails a dirty worktree | Builds immutable full-SHA tags and adds the OCI revision label | Local evidence proves source revision only, not that a registry/deployment contains it. |
| Alembic | Requires one head, exactly `0023_organisation_invitation_delivery` | Portal tests exercise migration code; deploy rollout is migration-gated | Exact-head proof is present locally and covered by the release-evidence unit contract. |
| Image identity | No registry or cluster access | Build outputs a full-SHA image tag; protected verification compares the workload image string | The workflows do not capture the pushed registry digest. A SHA tag and OCI revision label are useful but are not digest proof. Record the resolved `sha256:` digest separately before GO. |
| Freshness | JSON has UTC `generated_at`; portal fails closed after 24 hours | Workflow run and deployment verification timestamps exist in Actions | Release evidence freshness is enforced by the portal. Deployment freshness still needs a candidate record linking run, digest/revision, configuration revision, and UTC verification time. |
| Python | Prefers `platform-portal/.venv`, otherwise the invoking interpreter | Relevant portal workflows now consume `.python-version` (`3.12.13`) | This checkout's default `python3` was 3.14.4 and no portal venv existed. Create/recreate a 3.12.13 venv for exact local parity. |
| Portal pytest | Runs from `platform-portal/`, unsetting PostgreSQL URL | Runs `pytest ... platform-portal/tests` from repository root | Both select the portal suite, but working directory and invocation differ. Root bare `pytest` is broader and, in this checkout, collection fails without `SECRET_KEY`; it is not the release-evidence command. |
| PostgreSQL | Optional and skipped without `POSTGRES_TEST_DATABASE_URL`; configured mode resets a disposable local DB via `sudo -u postgres` | Current portal jobs do not declare a PostgreSQL service | `psql`/`pg_isready` were installed locally but no server answered on the default socket. PostgreSQL proof is therefore absent from this audit and must not be inferred from SQLite tests. |
| Playwright | Separate from release-evidence | Installs Chromium and OS dependencies with `npx playwright install --with-deps chromium` | Local runs need the same browser install plus `E2E_TEST_ONLY=1`; remote targets are fail-closed. Failure artifacts now include the configured `.tmp/playwright-test-results` directory. |
| Secrets/environment | Unsets PostgreSQL URL for the core portal suite; writes sanitized bounded output | PR tests need no cloud credentials; main publish/verify uses protected environment OIDC values | Required deployment variables are Azure client/tenant/subscription IDs and AKS resource group/cluster name. Terraform refers to same-named secrets. Renovate alone needs `RENOVATE_TOKEN`. Runtime `DATABASE_URL` and `SECRET_KEY` come from cluster secret references, not test-job secrets. |

## Command expectations

For a disposable local parity run using Python 3.12.13:

```sh
scripts/release/release-evidence --repo-root "$PWD"
python3 -m unittest discover -s scripts/release/tests -v
npm ci
npx playwright install --with-deps chromium
E2E_TEST_ONLY=1 npm run e2e
```

The first command also requires Ruff, Helm, and Terraform and fails closed when
a mandatory executable is missing. It writes JSON and Markdown under
`evidence/release/` by default. Because writing those files makes the worktree
dirty, generate final candidate evidence from an already clean candidate and
store/attach the outputs according to the acceptance record rather than
mistaking a subsequent dirty run for READY.

## Remaining release-evidence gaps

- No PostgreSQL service was available for this local audit.
- No registry digest, deployed workload digest, Argo revision, or live
  verification timestamp was collected; doing so is deliberately outside this
  repository-only task.
- The current deployment workflows compare an expected full-SHA tag to the
  workload image string. A final release record should additionally retain the
  resolved immutable registry digest and prove the running container image ID
  corresponds to it.
- Playwright results belong to the separate E2E triage effort and are not
  claimed by this report.
