#!/usr/bin/env python3
"""Generate local, non-deploying release-readiness evidence."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

EXIT_READY = 0
EXIT_NOT_READY = 1
EXIT_ERROR = 2
MAX_OUTPUT = 4_000
EXPECTED_ALEMBIC_HEAD = "0026_programming_exposure_roles"

SECRET_PATTERNS = (
    (re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)(\s*[=:]\s*)\S+"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:)[^@\s]+@"), r"\1[REDACTED]@"),
    (re.compile(r"(?i)(authorization:\s*(?:bearer|basic)\s+)\S+"), r"\1[REDACTED]"),
)


@dataclass
class Check:
    name: str
    status: str
    mandatory: bool
    summary: str
    command: list[str] | None = None
    output: str = ""
    duration_seconds: float = 0.0


def sanitize(value: str) -> str:
    """Redact common secret shapes and bound evidence size."""
    for pattern, replacement in SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    value = value.replace(str(Path.home()), "[HOME]")
    if len(value) > MAX_OUTPUT:
        value = value[:MAX_OUTPUT] + "\n[output truncated]"
    return value.strip()


def run_command(name: str, command: Sequence[str], cwd: Path, mandatory: bool = True) -> Check:
    executable = command[0]
    if shutil.which(executable) is None and not Path(executable).is_file():
        status = "fail" if mandatory else "skipped"
        return Check(name, status, mandatory, f"required executable not found: {executable}", list(command))
    started = datetime.now(timezone.utc)
    try:
        completed = subprocess.run(
            list(command), cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=900, check=False,
        )
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        output = sanitize(completed.stdout)
        return Check(
            name, "pass" if completed.returncode == 0 else "fail", mandatory,
            "command completed successfully" if completed.returncode == 0 else f"command exited {completed.returncode}",
            list(command), output, elapsed,
        )
    except subprocess.TimeoutExpired as exc:
        output = sanitize((exc.stdout or "") if isinstance(exc.stdout, str) else "")
        return Check(name, "fail", mandatory, "command timed out after 900 seconds", list(command), output, 900.0)
    except OSError as exc:
        return Check(name, "fail" if mandatory else "skipped", mandatory, sanitize(str(exc)), list(command))


def git_value(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=True,
    )
    return result.stdout.strip()


def find_merge_markers(root: Path) -> Check:
    pattern = re.compile(r"^(<<<<<<< |=======\s*$|>>>>>>> )")
    matches: list[str] = []
    tracked = git_value(root, "ls-files", "-z").split("\0")
    for relative in filter(None, tracked):
        path = root / relative
        try:
            with path.open("r", encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    if pattern.match(line):
                        matches.append(f"{relative}:{number}")
        except (UnicodeDecodeError, OSError):
            continue
    return Check(
        "unresolved_merge_markers", "fail" if matches else "pass", True,
        f"found {len(matches)} unresolved merge marker(s)" if matches else "no unresolved merge markers",
        output="\n".join(matches),
    )


def document_check(root: Path, expected: Sequence[str]) -> Check:
    missing = [item for item in expected if not (root / item).is_file()]
    return Check(
        "expected_release_documents", "fail" if missing else "pass", True,
        f"missing {len(missing)} expected document(s)" if missing else f"all {len(expected)} expected documents are present",
        output="\n".join(missing),
    )


def migration_heads_check(
    portal: Path, python: str, expected_head: str = EXPECTED_ALEMBIC_HEAD
) -> Check:
    check = run_command(
        "migration_heads",
        [python, "-m", "alembic", "-c", "migrations/alembic.ini", "heads"],
        portal,
    )
    if check.status == "pass":
        heads = [line for line in check.output.splitlines() if line.strip()]
        revisions = [line.split()[0] for line in heads]
        if len(heads) != 1:
            check.status = "fail"
            check.summary = f"expected exactly one migration head, found {len(heads)}"
        elif revisions[0] != expected_head:
            check.status = "fail"
            check.summary = (
                f"expected migration head {expected_head}, found {revisions[0]}"
            )
        else:
            check.summary = f"expected migration head: {heads[0]}"
    return check


def render_markdown(evidence: dict) -> str:
    lines = [
        "# Release readiness report", "",
        f"- Status: **{evidence['status'].upper()}**",
        f"- Generated: `{evidence['generated_at']}`",
        f"- Branch: `{evidence['repository']['branch']}`",
        f"- Commit: `{evidence['repository']['commit']}`",
        f"- Dirty worktree: `{'yes' if evidence['repository']['dirty'] else 'no'}`",
        "", "## Checks", "",
        "| Check | Required | Result | Summary |", "|---|---:|---:|---|",
    ]
    for check in evidence["checks"]:
        summary = check["summary"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{check['name']}` | {'yes' if check['mandatory'] else 'no'} | **{check['status']}** | {summary} |")
    lines.extend(["", "Detailed, sanitized command output is available in the JSON evidence file.", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="repository root (default: current directory)")
    parser.add_argument("--output-dir", type=Path, help="report directory (default: <repo>/evidence/release)")
    parser.add_argument("--json-name", default="release-evidence.json")
    parser.add_argument("--markdown-name", default="release-report.md")
    parser.add_argument("--expected-document", action="append", dest="documents", help="required path relative to root; repeatable")
    parser.add_argument("--quiet", action="store_true", help="suppress the terminal summary")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repo_root.expanduser().resolve()
    if not (root / ".git").exists() or not (root / "platform-portal").is_dir():
        print(f"release-evidence: invalid repository root: {root}", file=sys.stderr)
        return EXIT_ERROR
    output_dir = (args.output_dir or root / "evidence" / "release").expanduser().resolve()
    documents = args.documents or [
        "docs/release/README.md", "docs/release/release-checklist.md", "docs/release/rollback-plan.md",
    ]
    try:
        branch = git_value(root, "branch", "--show-current") or "DETACHED"
        commit = git_value(root, "rev-parse", "HEAD")
        dirty = bool(git_value(root, "status", "--porcelain"))
    except (subprocess.CalledProcessError, OSError) as exc:
        print(f"release-evidence: unable to inspect git repository: {sanitize(str(exc))}", file=sys.stderr)
        return EXIT_ERROR

    portal = root / "platform-portal"
    venv_bin = portal / ".venv" / "bin"
    portal_python = str(venv_bin / "python")
    portal_ruff = str(venv_bin / "ruff")

    if not Path(portal_python).is_file():
        portal_python = sys.executable

    if not Path(portal_ruff).is_file():
        portal_ruff = "ruff"

    checks = [
        run_command("ruff", [portal_ruff, "check", "."], portal),
        run_command(
            "format_check",
            [portal_ruff, "format", "--check", "."],
            portal,
        ),
        run_command(
            "pytest",
            [
                "bash",
                "-lc",
                f"unset POSTGRES_TEST_DATABASE_URL; {portal_python} -m pytest -q",
            ],
            portal,
        ),
        migration_heads_check(portal, portal_python),
    ]
    if os.getenv("POSTGRES_TEST_DATABASE_URL"):
        reset_command = [
            "bash",
            "-lc",
            "sudo -u postgres dropdb --if-exists traditional_strength_test "
            "&& sudo -u postgres createdb -O ts_app traditional_strength_test "
            "&& "
            + portal_python
            + " -m pytest -q "
            "tests/test_database_migrations.py "
            "tests/test_sqlite_postgres_migration.py",
        ]
        checks.append(
            run_command(
                "postgresql_tests",
                reset_command,
                portal,
            )
        )
    else:
        checks.append(Check("postgresql_tests", "skipped", False, "POSTGRES_TEST_DATABASE_URL is not configured"))
    checks.extend([
        run_command("helm_render", ["helm", "template", "flask-web-release-check", "flask-app", "-f", "flask-app/values-production.yaml"], root),
        run_command("terraform_format", ["terraform", "-chdir=infra", "fmt", "-check", "-recursive"], root),
        find_merge_markers(root),
        document_check(root, documents),
    ])
    checks.insert(0, Check(
        "worktree_clean", "fail" if dirty else "pass", True,
        "worktree has tracked or untracked changes" if dirty else "worktree is clean",
    ))
    status = "not_ready" if any(c.mandatory and c.status != "pass" for c in checks) else "ready"
    evidence = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "repository": {"branch": branch, "commit": commit, "dirty": dirty},
        "checks": [asdict(check) for check in checks],
    }
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / args.json_name
        markdown_path = output_dir / args.markdown_name
        json_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(render_markdown(evidence), encoding="utf-8")
    except OSError as exc:
        print(f"release-evidence: unable to write reports: {sanitize(str(exc))}", file=sys.stderr)
        return EXIT_ERROR

    if not args.quiet:
        print(f"Release readiness: {status.upper()}")
        print(f"Repository: {branch} @ {commit[:12]} ({'dirty' if dirty else 'clean'})")
        for check in checks:
            required = "required" if check.mandatory else "optional"
            print(f"  {check.status.upper():7} {check.name} ({required}) - {check.summary}")
        print(f"JSON: {json_path}")
        print(f"Markdown: {markdown_path}")
    return EXIT_READY if status == "ready" else EXIT_NOT_READY


if __name__ == "__main__":
    raise SystemExit(main())
