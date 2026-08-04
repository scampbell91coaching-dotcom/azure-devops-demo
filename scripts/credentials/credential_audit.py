#!/usr/bin/env python3
"""Audit credential metadata without reading credential values."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

SCHEMA_VERSION = "1.0"
MANIFEST_FIELDS = {"name", "owner", "last_verified", "storage_location", "rotation_status"}
ROTATION_STATUSES = {"current", "due", "required", "unknown"}
SECRET_FIELD_NAMES = {"value", "secret", "password", "token", "private_key", "connection_string"}
SOURCES = {"github", "azure"}
COVERAGE_STATES = {"complete", "partial", "unsupported", "unknown"}
COLLECTION_STATES = {"complete", "partial", "failed"}
SCOPE_FIELDS = ("repository", "environment", "subscription", "resource_group", "key_vault")


class AuditError(ValueError):
    """A safe, user-facing input error."""


def load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise AuditError(f"cannot read input file: {path}") from exc
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise AuditError(f"input is not valid UTF-8 JSON: {path}") from exc


def reject_secret_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in SECRET_FIELD_NAMES:
                raise AuditError("input contains a prohibited secret-value field")
            reject_secret_fields(child)
    elif isinstance(value, list):
        for child in value:
            reject_secret_fields(child)


def require_version(document: Any, label: str) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise AuditError(f"{label} inventory must be a JSON object")
    reject_secret_fields(document)
    if document.get("schema_version") != SCHEMA_VERSION:
        raise AuditError(f"{label} schema_version must be {SCHEMA_VERSION}")
    return document


def parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise AuditError(f"{field} must be a YYYY-MM-DD date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise AuditError(f"{field} must be a valid YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise AuditError(f"{field} must be a valid YYYY-MM-DD date")
    return parsed


def parse_manifest(document: Any) -> list[dict[str, str]]:
    data = require_version(document, "manifest")
    if set(data) != {"schema_version", "credentials"} or not isinstance(data["credentials"], list):
        raise AuditError("manifest must contain only schema_version and a credentials array")
    credentials: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(data["credentials"]):
        if not isinstance(item, dict) or set(item) != MANIFEST_FIELDS:
            raise AuditError(f"credentials[{index}] has invalid metadata fields")
        if not all(isinstance(item[field], str) and item[field].strip() for field in MANIFEST_FIELDS):
            raise AuditError(f"credentials[{index}] metadata fields must be non-empty strings")
        if item["rotation_status"] not in ROTATION_STATUSES:
            raise AuditError(f"credentials[{index}].rotation_status is invalid")
        parse_date(item["last_verified"], f"credentials[{index}].last_verified")
        if item["name"] in seen:
            raise AuditError("credential names must be unique")
        seen.add(item["name"])
        credentials.append({field: item[field] for field in sorted(MANIFEST_FIELDS)})
    return credentials


def parse_inventory(document: Any, expected_source: str) -> dict[str, Any]:
    """Validate and return a canonical producer secret-name projection."""
    data = require_version(document, expected_source.title())
    top_fields = {"schema_version", "source", "generated_at", "collection_status", "secret_scopes"}
    if set(data) != top_fields:
        raise AuditError(f"{expected_source.title()} inventory has invalid top-level fields")
    if data["source"] != expected_source or expected_source not in SOURCES:
        raise AuditError(f"inventory source must be {expected_source}")
    if data["collection_status"] not in COLLECTION_STATES:
        raise AuditError("inventory collection_status is invalid")
    if not isinstance(data["generated_at"], str):
        raise AuditError("inventory generated_at must be an RFC 3339 UTC timestamp")
    try:
        generated_at = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditError("inventory generated_at must be an RFC 3339 UTC timestamp") from exc
    if not data["generated_at"].endswith("Z") or generated_at.utcoffset() != timezone.utc.utcoffset(None):
        raise AuditError("inventory generated_at must be an RFC 3339 UTC timestamp")
    if not isinstance(data["secret_scopes"], list):
        raise AuditError("inventory secret_scopes must be an array")

    scopes: list[dict[str, Any]] = []
    seen_scopes: set[tuple[Any, ...]] = set()
    for index, item in enumerate(data["secret_scopes"]):
        if not isinstance(item, dict) or set(item) != {"scope", "coverage", "secret_names"}:
            raise AuditError(f"secret_scopes[{index}] has invalid fields")
        scope = item["scope"]
        if not isinstance(scope, dict) or set(scope) != set(SCOPE_FIELDS):
            raise AuditError(f"secret_scopes[{index}].scope has invalid fields")
        if any(value is not None and (not isinstance(value, str) or not value) for value in scope.values()):
            raise AuditError(f"secret_scopes[{index}].scope labels must be non-empty strings or null")
        if expected_source == "github":
            valid_scope = scope["repository"] is not None and all(scope[key] is None for key in SCOPE_FIELDS[2:])
        else:
            concrete = scope["resource_group"] is not None and scope["key_vault"] is not None
            aggregate = scope["resource_group"] is None and scope["key_vault"] is None
            valid_scope = scope["repository"] is None and scope["environment"] is None and scope["subscription"] is not None and (concrete or aggregate)
        if not valid_scope:
            raise AuditError(f"secret_scopes[{index}].scope is invalid for {expected_source}")
        scope_key = tuple(scope[key] for key in SCOPE_FIELDS)
        if scope_key in seen_scopes:
            raise AuditError("inventory scope tuples must be unique")
        seen_scopes.add(scope_key)
        coverage = item["coverage"]
        names = item["secret_names"]
        if coverage not in COVERAGE_STATES:
            raise AuditError(f"secret_scopes[{index}].coverage is invalid")
        if not isinstance(names, list) or any(not isinstance(name, str) or not name for name in names):
            raise AuditError(f"secret_scopes[{index}].secret_names must contain non-empty strings")
        if names != sorted(set(names)):
            raise AuditError(f"secret_scopes[{index}].secret_names must be sorted and unique")
        if coverage in {"unsupported", "unknown"} and names:
            raise AuditError(f"secret_scopes[{index}] cannot contain names for this coverage")
        scopes.append({"scope": dict(scope), "coverage": coverage, "secret_names": list(names)})
    if expected_source == "github":
        repositories = {entry["scope"]["repository"] for entry in scopes}
        repository_entries = [entry for entry in scopes if entry["scope"]["environment"] is None]
        if len(repositories) != 1 or len(repository_entries) != 1:
            raise AuditError("GitHub inventory must contain one repository and one repository scope")
    return {"source": expected_source, "collection_status": data["collection_status"], "secret_scopes": scopes}


def parse_github_inventory(document: Any) -> dict[str, Any]:
    return parse_inventory(document, "github")


def parse_azure_inventory(document: Any) -> dict[str, Any]:
    return parse_inventory(document, "azure")


def classify_coverage(location: str, inventories: dict[str, dict[str, Any] | None]) -> str:
    source: str | None = None
    wanted_scope: tuple[Any, ...] | None = None
    name: str | None = None
    if location.startswith("github-actions:repository:"):
        source, name = "github", location.removeprefix("github-actions:repository:")
        inventory = inventories.get(source)
        repository = inventory["secret_scopes"][0]["scope"]["repository"] if inventory else None
        wanted_scope = (repository, None, None, None, None)
    elif location.startswith("github-actions:environment:"):
        remainder = location.removeprefix("github-actions:environment:")
        try:
            encoded_environment, name = remainder.split(":", 1)
            environment = unquote(encoded_environment, errors="strict")
        except (ValueError, UnicodeError):
            return "unknown"
        if not encoded_environment or quote(environment, safe="-._~") != encoded_environment:
            return "unknown"
        source = "github"
        inventory = inventories.get(source)
        repository = inventory["secret_scopes"][0]["scope"]["repository"] if inventory else None
        wanted_scope = (repository, environment, None, None, None)
    elif location.startswith("azure-key-vault:"):
        parts = location.split(":", 4)
        if len(parts) != 5:
            return "unknown"
        _, subscription, resource_group, key_vault, name = parts
        source = "azure"
        wanted_scope = (None, None, subscription, resource_group, key_vault)
    if not source or not name or not all(part for part in wanted_scope if part is not None):
        return "unknown"
    inventory = inventories.get(source)
    if inventory is None:
        return "unknown"
    for entry in inventory["secret_scopes"]:
        scope_key = tuple(entry["scope"][key] for key in SCOPE_FIELDS)
        if scope_key != wanted_scope:
            continue
        if name in entry["secret_names"]:
            return "present"
        return "missing" if entry["coverage"] == "complete" else "unknown"
    return "unknown"


def audit(credentials: list[dict[str, str]], inventories: dict[str, dict[str, Any] | None], as_of: date, stale_days: int) -> dict[str, Any]:
    items = []
    counts = {key: 0 for key in ("present", "missing", "unknown", "stale", "rotation-required")}
    for credential in credentials:
        location = credential["storage_location"]
        coverage = classify_coverage(location, inventories)
        verified = parse_date(credential["last_verified"], "last_verified")
        stale = verified > as_of or (as_of - verified).days > stale_days
        rotation_required = credential["rotation_status"] in {"due", "required"}
        findings = [coverage]
        if stale:
            findings.append("stale")
        if rotation_required:
            findings.append("rotation-required")
        for finding in findings:
            counts[finding] += 1
        items.append({**credential, "coverage": coverage, "stale": stale, "rotation_required": rotation_required, "findings": findings})
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "as_of": as_of.isoformat(),
        "stale_after_days": stale_days,
        "inventory_inputs": {
            name: value["collection_status"] if value is not None else "not_supplied"
            for name, value in inventories.items()
        },
        "summary": counts,
        "credentials": items,
        "security_boundary": "Metadata only; no credential values were read or inferred from resource existence.",
    }


def markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Credential coverage audit", "", f"As of: `{report['as_of']}`  ",
        f"Stale after: `{report['stale_after_days']}` days", "",
        "| Present | Missing | Unknown | Stale | Rotation required |", "| ---: | ---: | ---: | ---: | ---: |",
        f"| {summary['present']} | {summary['missing']} | {summary['unknown']} | {summary['stale']} | {summary['rotation-required']} |", "",
        "| Credential | Owner | Storage location | Last verified | Rotation | Findings |", "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["credentials"]:
        safe = [str(item[key]).replace("|", "\\|").replace("\n", " ") for key in ("name", "owner", "storage_location", "last_verified", "rotation_status")]
        lines.append(f"| {' | '.join(safe)} | {', '.join(item['findings'])} |")
    lines.extend(["", f"> {report['security_boundary']}", ""])
    return "\n".join(lines)


def write_reports(output_dir: Path, report: dict[str, Any]) -> None:
    """Write the two metadata-only reports, presenting filesystem failures safely."""
    try:
        output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        output_dir.chmod(0o700)
        for filename, content in (
            ("credential-audit.json", json.dumps(report, indent=2) + "\n"),
            ("credential-audit.md", markdown(report)),
        ):
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{filename}.", dir=output_dir)
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary_name, output_dir / filename)
            except BaseException:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                try:
                    os.unlink(temporary_name)
                except OSError:
                    pass
                raise
    except OSError as exc:
        raise AuditError("cannot write credential audit reports") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--github-inventory", type=Path)
    parser.add_argument("--azure-inventory", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("evidence/credential-audit"))
    parser.add_argument("--as-of", type=lambda value: parse_date(value, "--as-of"), default=date.today())
    parser.add_argument("--stale-days", type=int, default=90)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.stale_days < 0:
            raise AuditError("--stale-days must be zero or greater")
        credentials = parse_manifest(load_json(args.manifest))
        inventories = {
            "github": parse_github_inventory(load_json(args.github_inventory)) if args.github_inventory else None,
            "azure": parse_azure_inventory(load_json(args.azure_inventory)) if args.azure_inventory else None,
        }
        report = audit(credentials, inventories, args.as_of, args.stale_days)
        write_reports(args.output_dir, report)
    except AuditError as exc:
        print(f"credential-audit: {exc}", file=sys.stderr)
        return 2
    print(f"Credential metadata reports written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
