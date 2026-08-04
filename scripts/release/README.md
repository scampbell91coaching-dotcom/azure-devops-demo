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
