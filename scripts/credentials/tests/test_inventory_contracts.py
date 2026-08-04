import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "credential_audit.py"
SPEC = importlib.util.spec_from_file_location("credential_audit_contract", MODULE_PATH)
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)
FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def credential(name, location):
    return {"name": name, "owner": "Platform", "last_verified": "2026-08-01", "storage_location": location, "rotation_status": "current"}


def test_actual_github_producer_fixture_is_consumed_without_reshaping():
    inventory = audit_module.parse_github_inventory(fixture("github-secret-name-inventory.v1.json"))
    items = [
        credential("repo", "github-actions:repository:DEPLOY_TOKEN"),
        credential("environment", "github-actions:environment:prod%2Feu:AZURE_ID"),
        credential("absent", "github-actions:repository:NOT_THERE"),
    ]
    report = audit_module.audit(items, {"github": inventory, "azure": None}, date(2026, 8, 4), 90)
    assert [item["coverage"] for item in report["credentials"]] == ["present", "present", "missing"]


def test_actual_azure_unsupported_fixture_is_unknown_not_missing():
    inventory = audit_module.parse_azure_inventory(fixture("azure-secret-name-inventory-unsupported.v1.json"))
    item = credential("azure", "azure-key-vault:00000000-0000-0000-0000-000000000001:rg-production:kv-production:app-database-url")
    report = audit_module.audit([item], {"github": None, "azure": inventory}, date(2026, 8, 4), 90)
    assert report["credentials"][0]["coverage"] == "unknown"
    assert report["inventory_inputs"]["azure"] == "partial"


def test_complete_azure_fixture_obeys_exact_scope_semantics():
    inventory = audit_module.parse_azure_inventory(fixture("azure-secret-name-inventory-complete.v1.json"))
    prefix = "azure-key-vault:00000000-0000-0000-0000-000000000001:rg-production:kv-production:"
    items = [credential("present", prefix + "app-database-url"), credential("missing", prefix + "other"), credential("other-vault", prefix.replace("kv-production", "kv-other") + "app-database-url")]
    report = audit_module.audit(items, {"github": None, "azure": inventory}, date(2026, 8, 4), 90)
    assert [item["coverage"] for item in report["credentials"]] == ["present", "missing", "unknown"]


@pytest.mark.parametrize("mutation", ["numeric_version", "missing_version", "extra", "value", "duplicate", "unsorted"])
def test_contract_rejects_invalid_fixture_mutations_without_leaking(mutation):
    document = fixture("github-secret-name-inventory.v1.json")
    marker = "DO-NOT-LEAK-THIS"
    if mutation == "numeric_version": document["schema_version"] = 1
    elif mutation == "missing_version": del document["schema_version"]
    elif mutation == "extra": document["unexpected"] = True
    elif mutation == "value": document["secret_scopes"][0]["value"] = marker
    elif mutation == "duplicate": document["secret_scopes"][0]["secret_names"] *= 2
    elif mutation == "unsorted": document["secret_scopes"][0]["secret_names"] = ["Z", "A"]
    with pytest.raises(audit_module.AuditError) as caught:
        audit_module.parse_github_inventory(document)
    assert marker not in str(caught.value)


def test_partial_unknown_and_aggregate_scopes_never_prove_absence():
    github = fixture("github-secret-name-inventory.v1.json")
    github["secret_scopes"][1].update(coverage="partial", secret_names=["AZURE_ID"])
    parsed = audit_module.parse_github_inventory(github)
    inventories = {"github": parsed, "azure": None}
    assert audit_module.classify_coverage("github-actions:environment:prod%2Feu:AZURE_ID", inventories) == "present"
    assert audit_module.classify_coverage("github-actions:environment:prod%2Feu:OTHER", inventories) == "unknown"
    azure = fixture("azure-secret-name-inventory-unsupported.v1.json")
    azure["secret_scopes"][0]["scope"].update(resource_group=None, key_vault=None)
    azure["secret_scopes"][0]["coverage"] = "unknown"
    parsed_azure = audit_module.parse_azure_inventory(azure)
    assert audit_module.classify_coverage("azure-key-vault:00000000-0000-0000-0000-000000000001:rg-production:kv-production:x", {"github": None, "azure": parsed_azure}) == "unknown"


def test_cli_rejects_wrong_source_and_accepts_both_producer_fixtures(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": "1.0", "credentials": [credential("repo", "github-actions:repository:DEPLOY_TOKEN")]}), encoding="utf-8")
    github = FIXTURES / "github-secret-name-inventory.v1.json"
    azure = FIXTURES / "azure-secret-name-inventory-unsupported.v1.json"
    wrong = subprocess.run([sys.executable, str(MODULE_PATH), "--manifest", str(manifest), "--azure-inventory", str(github), "--output-dir", str(tmp_path / "wrong")], capture_output=True, text=True)
    assert wrong.returncode == 2
    output = tmp_path / "evidence" / "credential-audit"
    valid = subprocess.run([sys.executable, str(MODULE_PATH), "--manifest", str(manifest), "--github-inventory", str(github), "--azure-inventory", str(azure), "--output-dir", str(output), "--as-of", "2026-08-04"], capture_output=True, text=True)
    assert valid.returncode == 0, valid.stderr
    serialized = (output / "credential-audit.json").read_text() + (output / "credential-audit.md").read_text()
    assert '"value"' not in serialized and '"secret"' not in serialized
