#!/usr/bin/env python3
"""Create a sanitized, read-only inventory of the active Azure subscription."""

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
from typing import Any, Sequence

EXIT_OK = 0
EXIT_ERROR = 2
SCHEMA_VERSION = "1.0"
TIMEOUT_SECONDS = 120

RESOURCE_QUERY = (
    "[].{id:id,name:name,resourceGroup:resourceGroup,location:location,type:type,"
    "kind:kind,sku:sku.name,status:properties.provisioningState}"
)
GROUP_QUERY = (
    "[].{id:id,name:name,resourceGroup:name,location:location,"
    "type:type,status:properties.provisioningState}"
)
ACCOUNT_QUERY = "{id:id,name:name,state:state,tenantId:tenantId,isDefault:isDefault}"


@dataclass(frozen=True)
class Collection:
    name: str
    resource_types: tuple[str, ...]


COLLECTIONS = (
    Collection("aks_clusters", ("Microsoft.ContainerService/managedClusters",)),
    Collection("acr_registries", ("Microsoft.ContainerRegistry/registries",)),
    Collection("postgresql_resources", (
        "Microsoft.DBforPostgreSQL/flexibleServers",
        "Microsoft.DBforPostgreSQL/servers",
    )),
    Collection("key_vaults", ("Microsoft.KeyVault/vaults",)),
    Collection("managed_identities", ("Microsoft.ManagedIdentity/userAssignedIdentities",)),
    Collection("dns_zones", (
        "Microsoft.Network/dnsZones",
        "Microsoft.Network/privateDnsZones",
    )),
    Collection("public_ips", ("Microsoft.Network/publicIPAddresses",)),
    Collection("vnets", ("Microsoft.Network/virtualNetworks",)),
)

SENSITIVE_KEY = re.compile(
    r"(?i)(password|passwd|credential|connection.?string|secret|token|access.?key|private.?key|kubeconfig)"
)
SENSITIVE_TEXT = (
    (re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key)(\s*[=:]\s*)\S+"), r"\1\2[REDACTED]"),
    (re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:)[^@\s]+@"), r"\1[REDACTED]@"),
    (re.compile(r"(?i)(authorization:\s*(?:bearer|basic)\s+)\S+"), r"\1[REDACTED]"),
)


class AzureCommandError(RuntimeError):
    def __init__(self, kind: str, returncode: int = 1):
        super().__init__(safe_error(kind))
        self.kind = kind
        self.returncode = returncode


def safe_error(kind: str) -> str:
    return {
        "permission_limited": "Azure metadata access was denied",
        "provider_unavailable": "Azure resource provider is unavailable",
        "timeout": "Azure metadata request timed out",
        "cli_unavailable": "Azure CLI could not be executed",
        "invalid_response": "Azure CLI returned invalid metadata",
        "command_failed": "Azure metadata could not be retrieved",
    }.get(kind, "Azure metadata could not be retrieved")


def sanitize_text(value: str) -> str:
    for pattern, replacement in SENSITIVE_TEXT:
        value = pattern.sub(replacement, value)
    return value.strip()[:2000]


def sanitize(value: Any) -> Any:
    """Defensively remove sensitive keys and redact common secret-shaped strings."""
    if isinstance(value, dict):
        return {
            str(key): sanitize(item)
            for key, item in value.items()
            if not SENSITIVE_KEY.search(str(key))
        }
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def az_json(arguments: Sequence[str]) -> Any:
    command = ["az", *arguments, "--only-show-errors", "--output", "json"]
    try:
        completed = subprocess.run(
            command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AzureCommandError("timeout") from exc
    except OSError as exc:
        raise AzureCommandError("cli_unavailable") from exc
    if completed.returncode:
        raise AzureCommandError(issue_kind(completed.stderr), completed.returncode)
    try:
        return sanitize(json.loads(completed.stdout))
    except json.JSONDecodeError as exc:
        raise AzureCommandError("invalid_response") from exc


def issue_kind(message: str) -> str:
    lowered = message.lower()
    if any(term in lowered for term in ("authorizationfailed", "forbidden", "does not have authorization", "permission")):
        return "permission_limited"
    if any(term in lowered for term in ("missingregistration", "not registered", "resource provider", "namespace")):
        return "provider_unavailable"
    return "command_failed"


def resource_command(resource_type: str) -> list[str]:
    return ["resource", "list", "--resource-type", resource_type, "--query", RESOURCE_QUERY]


def collect_inventory() -> dict[str, Any]:
    subscription = az_json(["account", "show", "--query", ACCOUNT_QUERY])
    resources: dict[str, list[dict[str, Any]]] = {}
    issues: list[dict[str, str]] = []
    try:
        groups = az_json(["group", "list", "--query", GROUP_QUERY])
        resources["resource_groups"] = groups if isinstance(groups, list) else []
    except AzureCommandError as exc:
        resources["resource_groups"] = []
        issues.append({"collection": "resource_groups", "kind": exc.kind, "message": safe_error(exc.kind)})

    for collection in COLLECTIONS:
        collected: list[dict[str, Any]] = []
        for resource_type in collection.resource_types:
            try:
                result = az_json(resource_command(resource_type))
                if isinstance(result, list):
                    collected.extend(result)
            except AzureCommandError as exc:
                issues.append({
                    "collection": collection.name,
                    "resource_type": resource_type,
                    "kind": exc.kind,
                    "message": safe_error(exc.kind),
                })
        resources[collection.name] = collected

    return sanitize({
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "subscription": subscription,
        "status": "complete" if not issues else "partial",
        "resources": resources,
        "issues": issues,
    })


def secret_name_projection(inventory: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical metadata-only contract without querying secret names."""
    subscription_id = inventory.get("subscription", {}).get("id")
    vaults = inventory.get("resources", {}).get("key_vaults", [])
    discovery_failed = any(
        issue.get("collection") == "key_vaults" for issue in inventory.get("issues", [])
    )
    if discovery_failed:
        scopes = [{"scope": {"repository": None, "environment": None,
                              "subscription": subscription_id, "resource_group": None,
                              "key_vault": None}, "coverage": "unknown", "secret_names": []}]
        status = "failed"
    elif vaults:
        scopes = [{"scope": {"repository": None, "environment": None,
                              "subscription": subscription_id,
                              "resource_group": vault.get("resourceGroup"),
                              "key_vault": vault.get("name")},
                   "coverage": "unsupported", "secret_names": []}
                  for vault in sorted(vaults, key=lambda item: (
                      str(item.get("resourceGroup")), str(item.get("name"))))]
        status = "partial"
    else:
        scopes = [{"scope": {"repository": None, "environment": None,
                              "subscription": subscription_id, "resource_group": None,
                              "key_vault": None}, "coverage": "complete", "secret_names": []}]
        status = "complete"
    return {"schema_version": SCHEMA_VERSION, "source": "azure",
            "generated_at": inventory["generated_at"], "collection_status": status,
            "secret_scopes": scopes}


def write_private(path: Path, content: str) -> None:
    """Atomically replace a report with mode 0600."""
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def markdown_escape(value: Any) -> str:
    return str(value if value not in (None, "") else "-").replace("|", "\\|").replace("\n", " ")


def render_markdown(inventory: dict[str, Any]) -> str:
    subscription = inventory["subscription"]
    lines = [
        "# Azure metadata inventory", "",
        f"- Generated: `{markdown_escape(inventory['generated_at'])}`",
        f"- Collection status: **{inventory['status'].upper()}**",
        f"- Active subscription: `{markdown_escape(subscription.get('name'))}` (`{markdown_escape(subscription.get('id'))}`)",
        f"- Subscription state: `{markdown_escape(subscription.get('state'))}`", "",
    ]
    for name, items in inventory["resources"].items():
        lines.extend([
            f"## {name.replace('_', ' ').title()} ({len(items)})", "",
            "| Name | Resource group | Region | Type | Status | Resource ID |",
            "|---|---|---|---|---|---|",
        ])
        for item in items:
            status = item.get("status") or item.get("sku") or item.get("kind")
            lines.append("| " + " | ".join(markdown_escape(item.get(field)) for field in (
                "name", "resourceGroup", "location", "type"
            )) + f" | {markdown_escape(status)} | {markdown_escape(item.get('id'))} |")
        if not items:
            lines.append("| _None returned_ | - | - | - | - | - |")
        lines.append("")
    lines.extend(["## Collection issues", ""])
    if inventory["issues"]:
        lines.extend(["| Collection | Kind | Message |", "|---|---|---|"])
        for issue in inventory["issues"]:
            lines.append(f"| {markdown_escape(issue['collection'])} | {markdown_escape(issue['kind'])} | {markdown_escape(issue['message'])} |")
    else:
        lines.append("No collection issues were reported.")
    lines.extend(["", "This report contains metadata only. It does not query credentials, keys, secrets, tokens, connection strings, or kubeconfigs.", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("evidence/azure-inventory"))
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if shutil.which("az") is None:
        print("azure-inventory: Azure CLI executable not found", file=sys.stderr)
        return EXIT_ERROR
    try:
        inventory = collect_inventory()
        projection = secret_name_projection(inventory)
        output_dir = args.output_dir.expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(output_dir, 0o700)
        json_path = output_dir / "azure-inventory.json"
        markdown_path = output_dir / "azure-inventory.md"
        contract_path = output_dir / "azure-secret-name-inventory.json"
        write_private(json_path, json.dumps(inventory, indent=2) + "\n")
        write_private(markdown_path, render_markdown(inventory))
        write_private(contract_path, json.dumps(projection, indent=2) + "\n")
    except AzureCommandError as exc:
        print(f"azure-inventory: {safe_error(exc.kind)}", file=sys.stderr)
        return EXIT_ERROR
    except OSError:
        print("azure-inventory: could not write private inventory reports", file=sys.stderr)
        return EXIT_ERROR
    if not args.quiet:
        print(f"Azure inventory: {inventory['status'].upper()}")
        print(f"JSON: {json_path}")
        print(f"Markdown: {markdown_path}")
        print(f"Secret-name contract: {contract_path}")
        for issue in inventory["issues"]:
            print(f"  {issue['kind']}: {issue['collection']}")
    incomplete = inventory["status"] != "complete" or projection["collection_status"] != "complete"
    return EXIT_ERROR if args.require_complete and incomplete else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
