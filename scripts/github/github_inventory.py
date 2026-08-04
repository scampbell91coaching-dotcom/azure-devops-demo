#!/usr/bin/env python3
"""Collect a sanitized, read-only GitHub metadata inventory using gh."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import quote

EXIT_OK = 0
EXIT_ERROR = 2
SCHEMA_VERSION = "1.0"
SENSITIVE_KEY = re.compile(r"(?i)(secret|token|password|credential|private.?key|\bvalue\b)")
AUTH_FAILURE = re.compile(r"(?i)(not logged|authenticate|authentication|401|bad credentials)")
DENIED_FAILURE = re.compile(r"(?i)(403|forbidden|resource not accessible|permission|not authorized|not authorised)")


@dataclass
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[[Sequence[str], Path], CommandResult]


def subprocess_runner(command: Sequence[str], cwd: Path) -> CommandResult:
    try:
        completed = subprocess.run(
            list(command), cwd=cwd, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(124, stderr="GitHub CLI timed out")
    except OSError:
        return CommandResult(127, stderr="GitHub CLI is unavailable")
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def classify_failure(result: CommandResult) -> str:
    message = f"{result.stderr}\n{result.stdout}"
    if AUTH_FAILURE.search(message):
        return "unauthenticated"
    if DENIED_FAILURE.search(message):
        return "unauthorized"
    return "unavailable"


def safe_error(result: CommandResult) -> str:
    """Return a bounded error category, never raw CLI/API output."""
    return {
        "unauthenticated": "GitHub authentication is required",
        "unauthorized": "the authenticated identity lacks permission",
        "unavailable": "GitHub metadata could not be retrieved",
    }[classify_failure(result)]


def sanitize(
    value: Any,
    *,
    allowed_secret_paths: frozenset[tuple[str, ...]] = frozenset(),
    _path: tuple[str, ...] = (),
) -> Any:
    """Recursively remove sensitive-looking fields from unexpected data."""
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            key = str(key)
            child_path = _path + (key,)
            path_pattern = tuple("*" if part.isdigit() else part for part in child_path)
            if SENSITIVE_KEY.search(key) and path_pattern not in allowed_secret_paths:
                continue
            clean[key] = sanitize(
                item, allowed_secret_paths=allowed_secret_paths, _path=child_path
            )
        return clean
    if isinstance(value, list):
        return [
            sanitize(item, allowed_secret_paths=allowed_secret_paths, _path=_path + (str(index),))
            for index, item in enumerate(value)
        ]
    if isinstance(value, str):
        return value[:2000]
    return value


def parse_json(result: CommandResult) -> Any:
    if result.returncode != 0:
        raise ValueError("command failed")
    try:
        return json.loads(result.stdout or "null")
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON returned by gh") from exc


class InventoryCollector:
    def __init__(self, root: Path, runner: Runner = subprocess_runner, repo: str | None = None):
        self.root = root
        self.runner = runner
        self.repo_override = repo
        self.repo = repo

    def run(self, *args: str) -> CommandResult:
        return self.runner(["gh", *args], self.root)

    def endpoint(self, suffix: str) -> str:
        if not self.repo:
            raise RuntimeError("repository identity is unavailable")
        return f"repos/{self.repo}/{suffix}"

    @staticmethod
    def section(status: str, items: list[dict[str, Any]] | None = None, detail: str | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {"status": status, "items": items or []}
        if detail:
            data["detail"] = detail
        return data

    def api(self, endpoint: str) -> CommandResult:
        return self.run("api", "--method", "GET", endpoint, "--paginate", "--slurp")

    def collect_list(self, endpoint: str, key: str, fields: Sequence[str]) -> dict[str, Any]:
        result = self.api(endpoint)
        if result.returncode != 0:
            status = classify_failure(result)
            return self.section(status, detail=safe_error(result))
        try:
            pages = parse_json(result)
            if not isinstance(pages, list):
                raise ValueError("expected paginated JSON list")
            source: list[Any] = []
            for page in pages:
                if isinstance(page, dict) and isinstance(page.get(key), list):
                    source.extend(page[key])
                elif isinstance(page, list):
                    source.extend(page)
            items = [
                {field: item.get(field) for field in fields if item.get(field) is not None}
                for item in source if isinstance(item, dict)
            ]
            return self.section("ok" if items else "empty", items)
        except ValueError:
            return self.section("unavailable", detail="GitHub returned invalid metadata")

    def collect(self) -> dict[str, Any]:
        auth = self.run("auth", "status")
        if auth.returncode != 0:
            status = classify_failure(auth)
            return self.base_result(status, safe_error(auth))

        identity_command = ["repo", "view"]
        if self.repo_override:
            identity_command.append(self.repo_override)
        identity_command.extend(["--json", "nameWithOwner,url,defaultBranchRef,isPrivate,visibility"])
        identity_result = self.run(*identity_command)
        if identity_result.returncode != 0:
            status = classify_failure(identity_result)
            return self.base_result(status, safe_error(identity_result))
        try:
            raw_identity = parse_json(identity_result)
            self.repo = raw_identity["nameWithOwner"]
            if not isinstance(self.repo, str) or not self.repo:
                raise ValueError("missing repository identity")
        except (ValueError, KeyError, TypeError):
            return self.base_result("unavailable", "GitHub returned invalid repository identity")

        identity = {
            field: raw_identity.get(field)
            for field in ("nameWithOwner", "url", "defaultBranchRef", "isPrivate", "visibility")
        }
        workflows = self.collect_list(
            self.endpoint("actions/workflows"), "workflows",
            ("id", "name", "path", "state", "created_at", "updated_at"),
        )
        variables = self.collect_list(
            self.endpoint("actions/variables"), "variables", ("name", "created_at", "updated_at"),
        )
        secrets = self.collect_list(
            self.endpoint("actions/secrets"), "secrets", ("name", "created_at", "updated_at"),
        )
        environments = self.collect_list(
            self.endpoint("environments"), "environments", ("name", "created_at", "updated_at", "protection_rules"),
        )
        for environment in environments["items"]:
            name = environment.get("name")
            if name:
                environment["secrets"] = self.collect_list(
                    self.endpoint(f"environments/{quote(str(name), safe='')}/secrets"),
                    "secrets", ("name", "created_at", "updated_at"),
                )

        default_branch = identity.get("defaultBranchRef", {}).get("name") if isinstance(identity.get("defaultBranchRef"), dict) else None
        protection = self.section("empty")
        if default_branch:
            result = self.run("api", "--method", "GET", self.endpoint(f"branches/{quote(default_branch, safe='')}/protection"))
            if result.returncode != 0:
                message = f"{result.stderr} {result.stdout}"
                status = "empty" if re.search(r"(?i)branch not protected", message) else classify_failure(result)
                protection = self.section(status, detail=None if status == "empty" else safe_error(result))
            else:
                try:
                    raw = parse_json(result)
                    allowed = ("required_status_checks", "enforce_admins", "required_pull_request_reviews", "restrictions", "required_linear_history", "allow_force_pushes", "allow_deletions", "required_conversation_resolution", "lock_branch", "allow_fork_syncing")
                    metadata = {key: raw[key] for key in allowed if isinstance(raw, dict) and key in raw}
                    protection = {"status": "ok", "metadata": sanitize(metadata)}
                except ValueError:
                    protection = self.section("unavailable", detail="GitHub returned invalid metadata")

        return sanitize({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok", "repository": identity, "workflows": workflows,
            "variables": variables, "secrets": secrets, "environments": environments,
            "default_branch_protection": protection,
        }, allowed_secret_paths=frozenset({
            ("secrets",), ("environments", "items", "*", "secrets"),
        }))

    @staticmethod
    def base_result(status: str, detail: str) -> dict[str, Any]:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": status, "detail": detail, "repository": None,
            "workflows": {"status": "unavailable", "items": []},
            "variables": {"status": "unavailable", "items": []},
            "secrets": {"status": "unavailable", "items": []},
            "environments": {"status": "unavailable", "items": []},
            "default_branch_protection": {"status": "unavailable", "items": []},
        }


def render_markdown(data: dict[str, Any]) -> str:
    def inline(value: Any) -> str:
        return str(value).replace("\r", " ").replace("\n", " ").replace("`", "'").replace("|", "\\|")

    repo = data.get("repository") or {}
    lines = [
        "# GitHub metadata inventory", "",
        f"- Generated: `{data['generated_at']}`",
        f"- Overall status: **{data['status']}**",
    ]
    if repo:
        lines.extend([
            f"- Repository: `{inline(repo.get('nameWithOwner', 'unknown'))}`",
            f"- Default branch: `{inline((repo.get('defaultBranchRef') or {}).get('name', 'unknown'))}`",
        ])
    if data.get("detail"):
        lines.append(f"- Detail: {data['detail']}")
    lines.extend(["", "## Collection status", "", "| Area | Status | Items |", "|---|---|---:|"])
    for key, title in (("workflows", "Workflows"), ("variables", "Variables"), ("secrets", "Repository secret names"), ("environments", "Environments"), ("default_branch_protection", "Default branch protection")):
        section = data[key]
        count = len(section.get("items", [])) if key != "default_branch_protection" else (1 if section.get("metadata") else 0)
        lines.append(f"| {title} | {section['status']} | {count} |")
    lines.extend(["", "## Metadata", ""])
    for key, title in (("workflows", "Workflows"), ("variables", "Repository variables"), ("secrets", "Repository secret names")):
        lines.extend([f"### {title}", ""])
        items = data[key].get("items", [])
        lines.extend([f"- `{inline(item.get('name', item.get('path', 'unnamed')))}`" for item in items] or [f"_No items ({data[key]['status']})._"])
        lines.append("")
    lines.extend(["### Environments", ""])
    for environment in data["environments"].get("items", []):
        secret_names = [item.get("name", "unnamed") for item in environment.get("secrets", {}).get("items", [])]
        rendered_names = ", ".join(f"`{inline(name)}`" for name in secret_names)
        lines.append(f"- `{inline(environment.get('name', 'unnamed'))}` — secrets: {rendered_names or environment.get('secrets', {}).get('status', 'not collected')}")
    if not data["environments"].get("items"):
        lines.append(f"_No items ({data['environments']['status']})._")
    lines.extend(["", "Secret and variable values are never requested or written.", ""])
    return "\n".join(lines)


def build_secret_name_inventory(data: dict[str, Any]) -> dict[str, Any]:
    """Build the strict shared v1.0 contract from allowlisted secret names."""
    repo = data.get("repository") or {}
    repository = repo.get("nameWithOwner")
    scopes: list[dict[str, Any]] = []

    def add_scope(environment: str | None, section: dict[str, Any]) -> None:
        native_status = section.get("status")
        coverage = "complete" if native_status in {"ok", "empty"} else "unknown"
        names = sorted({
            item["name"] for item in section.get("items", [])
            if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"]
        })
        if coverage == "unknown":
            names = []
        scopes.append({
            "scope": {
                "repository": repository, "environment": environment,
                "subscription": None, "resource_group": None, "key_vault": None,
            },
            "coverage": coverage,
            "secret_names": names,
        })

    if isinstance(repository, str) and repository:
        add_scope(None, data.get("secrets", {}))
        environments = data.get("environments", {})
        if environments.get("status") in {"ok", "empty"}:
            for environment in environments.get("items", []):
                name = environment.get("name") if isinstance(environment, dict) else None
                if isinstance(name, str) and name:
                    add_scope(name, environment.get("secrets", {}))

    scopes.sort(key=lambda entry: (entry["scope"]["environment"] is not None, entry["scope"]["environment"] or ""))
    if not scopes:
        collection_status = "failed"
    elif all(scope["coverage"] == "complete" for scope in scopes):
        collection_status = "complete"
    else:
        collection_status = "partial"
    generated_at = str(data.get("generated_at", ""))
    if generated_at.endswith("+00:00"):
        generated_at = generated_at[:-6] + "Z"
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "github",
        "generated_at": generated_at,
        "collection_status": collection_status,
        "secret_scopes": scopes,
    }


def write_private(path: Path, content: str) -> None:
    """Atomically replace a report while enforcing mode 0600."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        path.chmod(0o600)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="local repository (default: current directory)")
    parser.add_argument("--repo", help="GitHub OWNER/REPO override (default: repository associated with current directory)")
    parser.add_argument("--output-dir", type=Path, help="default: <repo>/evidence/github-inventory")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.repo_root.resolve()
    output = (args.output_dir or root / "evidence" / "github-inventory").resolve()
    if shutil.which("gh") is None:
        data = InventoryCollector.base_result("unavailable", "gh CLI is not installed")
    else:
        data = InventoryCollector(root, repo=args.repo).collect()
    try:
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        output.chmod(0o700)
        write_private(output / "github-inventory.json", json.dumps(data, indent=2) + "\n")
        write_private(output / "github-inventory.md", render_markdown(data))
        contract = build_secret_name_inventory(data)
        write_private(output / "github-secret-name-inventory.json", json.dumps(contract, indent=2) + "\n")
    except OSError as exc:
        print(f"github-inventory: unable to write reports: {exc.__class__.__name__}", file=sys.stderr)
        return EXIT_ERROR
    print(f"Wrote sanitized inventory to {output}")
    return EXIT_OK if data["status"] == "ok" else EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
