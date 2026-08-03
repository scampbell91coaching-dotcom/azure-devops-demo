# GitHub Actions toolchain compatibility

This repository uses GitHub-hosted `ubuntu-latest` runners. The August 2026
toolchain refresh makes the following compatibility decisions:

- `actions/checkout` moves from v4 to v6. Both v5 and v6 use the Node.js 24
  action runtime. GitHub-hosted runners satisfy checkout v6's runner
  requirements, including its credential storage under `RUNNER_TEMP`. Existing
  authenticated `git push` steps remain supported by checkout's default
  `persist-credentials: true` behaviour.
- `actions/setup-python` moves from v5 to v6. The major change is the Node.js 24
  action runtime and requires Actions Runner 2.327.1 or newer. Python 3.12 and
  pip caching inputs are unchanged.
- `actions/setup-node` moves from v4 to v6. The workflow already explicitly
  enables npm caching, so v6's automatic package-manager cache detection does
  not change behaviour. It does not use the removed `always-auth` input. The
  Node.js 24 action runtime requires Actions Runner 2.327.1 or newer; the tested
  application runtime remains Node.js 20.
- `github/codeql-action` moves from v3 to v4 before v3 deprecation. Existing
  Python initialization, `security-extended` queries, SARIF upload, categories,
  and `security-events: write` permissions remain compatible.
- `aquasecurity/trivy-action` remains on v0.36.0, pinned to the immutable full
  commit SHA for that release, while its scanner is explicitly upgraded to
  Trivy v0.73.0. The HIGH/CRITICAL gate, `ignore-unfixed`, non-zero exit code,
  vulnerability scanning, secret scanning, and SARIF upload are preserved.
  SARIF severity output is explicitly limited to the same severities as the
  failing gate.

Other action majors were deliberately retained where a current-major upgrade
would add unrelated migration risk or was not required by this refresh:

- Artifact upload/download stay on v4 because the paired Terraform plan
  hand-off already uses the compatible immutable-artifact backend; newer majors
  primarily change the action runtime and add artifact semantics not needed by
  these workflows.
- Azure login/setup-helm, Docker login, HashiCorp setup-terraform, and Anchore
  SBOM actions retain their existing majors because their current workflow
  inputs remain supported and no safe compatibility-driven major migration was
  identified for this change.

The Trivy action is SHA-pinned because scanner integrity is directly part of
the release gate. Other existing actions retain stable major-version references
and are never changed to floating branches such as `main`, `master`, or
`latest`.

## Platform Security failure

The failed job's SARIF-only scan concealed its findings from the log. A local
filesystem scan of the dependency lockfiles and repository contents found zero
HIGH/CRITICAL vulnerabilities and zero secrets after excluding only generated
directories (`.git`, `.venv`, `node_modules`, `test-results`, `evidence`, and
`.tmp`). No ignore file or vulnerability suppression is added, and no direct
dependency needs a security upgrade for this result. The CI diagnostic scan now
prints the same scoped HIGH/CRITICAL vulnerability and secret results as a
readable table before the blocking SARIF scan.

The workflow records the blocking Trivy step outcome, uploads SARIF and the
SBOM, and then fails the job when Trivy reports a finding. This corrects the
output-publication control flow without weakening the scanner's threshold,
`ignore-unfixed`, or exit code. SARIF is uploaded with `if: always()`, and
pull-request versus main triggers and least-privilege permissions are unchanged.
