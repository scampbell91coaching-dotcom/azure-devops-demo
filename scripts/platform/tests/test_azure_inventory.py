import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "azure_inventory.py"
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "azure-secret-name-inventory-unsupported.v1.json"
SPEC = importlib.util.spec_from_file_location("azure_inventory", MODULE_PATH)
azure_inventory = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = azure_inventory
SPEC.loader.exec_module(azure_inventory)


class AzureInventoryTests(unittest.TestCase):
    def test_resource_collections_use_only_generic_read_commands(self):
        expected_types = {
            "Microsoft.ContainerService/managedClusters",
            "Microsoft.ContainerRegistry/registries",
            "Microsoft.DBforPostgreSQL/flexibleServers",
            "Microsoft.DBforPostgreSQL/servers",
            "Microsoft.KeyVault/vaults",
            "Microsoft.ManagedIdentity/userAssignedIdentities",
            "Microsoft.Network/dnsZones",
            "Microsoft.Network/privateDnsZones",
            "Microsoft.Network/publicIPAddresses",
            "Microsoft.Network/virtualNetworks",
        }
        commands = [
            azure_inventory.resource_command(resource_type)
            for collection in azure_inventory.COLLECTIONS
            for resource_type in collection.resource_types
        ]

        self.assertEqual({command[3] for command in commands}, expected_types)
        self.assertTrue(all(command[:3] == ["resource", "list", "--resource-type"] for command in commands))
        self.assertTrue(all(command[-2:] == ["--query", azure_inventory.RESOURCE_QUERY] for command in commands))

    @mock.patch.object(azure_inventory.subprocess, "run")
    def test_az_json_builds_read_only_json_command(self, run):
        run.return_value = mock.Mock(returncode=0, stdout='[{"name":"demo"}]', stderr="")
        result = azure_inventory.az_json(azure_inventory.resource_command("Microsoft.Network/virtualNetworks"))
        self.assertEqual(result, [{"name": "demo"}])
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["az", "resource", "list", "--resource-type"])
        self.assertIn("--query", command)
        self.assertEqual(command[-3:], ["--only-show-errors", "--output", "json"])
        self.assertNotIn("show-connection-string", command)
        self.assertNotIn("get-credentials", command)

    @mock.patch.object(azure_inventory.subprocess, "run")
    def test_az_json_parses_and_redacts_sensitive_fields(self, run):
        run.return_value = mock.Mock(
            returncode=0,
            stdout=json.dumps({"name": "db", "password": "bad", "note": "token=abc123"}),
            stderr="",
        )
        result = azure_inventory.az_json(["account", "show"])
        self.assertNotIn("password", result)
        self.assertEqual(result["note"], "token=[REDACTED]")

    @mock.patch.object(azure_inventory.subprocess, "run")
    def test_az_json_sanitizes_failure_output(self, run):
        marker = "eyJhbGciOiJIUzI1NiJ9.payload.signature"
        run.return_value = mock.Mock(returncode=1, stdout="", stderr=f"Forbidden token={marker}")
        with self.assertRaises(azure_inventory.AzureCommandError) as caught:
            azure_inventory.az_json(["group", "list"])
        self.assertNotIn(marker, str(caught.exception))
        self.assertEqual(caught.exception.kind, "permission_limited")

    @mock.patch.object(azure_inventory.subprocess, "run")
    def test_failures_never_expose_jwt_sas_quoted_or_multiline_stderr(self, run):
        samples = [
            "eyJhbGciOiJIUzI1NiJ9.payload.signature",
            "https://account.blob.core.windows.net/c?sv=2025&sig=SECRET-SAS",
            'client_secret="QUOTED-SECRET"',
            "line one\npassword without separator SECRET-MULTILINE\nline three",
        ]
        for marker in samples:
            with self.subTest(marker=marker):
                run.return_value = mock.Mock(returncode=1, stdout="", stderr=marker)
                with self.assertRaises(azure_inventory.AzureCommandError) as caught:
                    azure_inventory.az_json(["group", "list"])
                self.assertEqual(str(caught.exception), "Azure metadata could not be retrieved")

    @mock.patch.object(azure_inventory.subprocess, "run")
    def test_az_json_rejects_invalid_json(self, run):
        run.return_value = mock.Mock(returncode=0, stdout="not-json", stderr="")

        with self.assertRaisesRegex(azure_inventory.AzureCommandError, "invalid metadata"):
            azure_inventory.az_json(["group", "list"])

    @mock.patch.object(azure_inventory.subprocess, "run")
    def test_az_json_reports_timeout_without_command_output(self, run):
        run.side_effect = azure_inventory.subprocess.TimeoutExpired(["az", "group", "list"], 120)

        with self.assertRaisesRegex(azure_inventory.AzureCommandError, "timed out") as caught:
            azure_inventory.az_json(["group", "list"])
        self.assertNotIn("az group list", str(caught.exception))

    @mock.patch.object(azure_inventory, "az_json")
    def test_collection_continues_after_provider_failure(self, az_json):
        def response(arguments):
            if arguments[:2] == ["account", "show"]:
                return {"id": "sub", "name": "demo", "state": "Enabled"}
            if "Microsoft.DBforPostgreSQL/flexibleServers" in arguments:
                raise azure_inventory.AzureCommandError("provider_unavailable")
            return []

        az_json.side_effect = response
        result = azure_inventory.collect_inventory()
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["resources"]["postgresql_resources"], [])
        self.assertTrue(any(issue["kind"] == "provider_unavailable" for issue in result["issues"]))

    @mock.patch.object(azure_inventory.shutil, "which", return_value="/usr/bin/az")
    @mock.patch.object(azure_inventory, "collect_inventory")
    def test_main_writes_json_and_markdown(self, collect, _which):
        collect.return_value = {
            "schema_version": "1.0", "generated_at": "2026-01-01T00:00:00Z", "status": "complete",
            "subscription": {"id": "sub", "name": "demo", "state": "Enabled"},
            "resources": {"resource_groups": [], "key_vaults": []}, "issues": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o755)
            code = azure_inventory.main(["--output-dir", directory, "--quiet"])
            self.assertEqual(code, 0)
            payload = json.loads((Path(directory) / "azure-inventory.json").read_text())
            self.assertEqual(payload["subscription"]["id"], "sub")
            self.assertTrue((Path(directory) / "azure-inventory.md").is_file())
            contract = json.loads((Path(directory) / "azure-secret-name-inventory.json").read_text())
            self.assertEqual(contract["schema_version"], "1.0")
            self.assertEqual(contract["collection_status"], "complete")
            self.assertEqual(stat.S_IMODE(Path(directory).stat().st_mode), 0o700)
            for report in Path(directory).iterdir():
                self.assertEqual(stat.S_IMODE(report.stat().st_mode), 0o600)

    def test_discovered_vault_is_explicitly_unsupported(self):
        inventory = {
            "generated_at": "2026-08-04T12:00:00Z",
            "subscription": {"id": "00000000-0000-0000-0000-000000000001"},
            "resources": {"key_vaults": [{"name": "kv-production", "resourceGroup": "rg-production"}]},
            "issues": [],
        }
        projection = azure_inventory.secret_name_projection(inventory)
        self.assertEqual(projection["collection_status"], "partial")
        self.assertEqual(projection["secret_scopes"][0]["coverage"], "unsupported")
        self.assertEqual(projection["secret_scopes"][0]["secret_names"], [])
        self.assertEqual(projection, json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))

    def test_failed_vault_discovery_is_unknown(self):
        inventory = {
            "generated_at": "2026-08-04T12:00:00Z", "subscription": {"id": "sub"},
            "resources": {"key_vaults": []},
            "issues": [{"collection": "key_vaults", "kind": "permission_limited"}],
        }
        projection = azure_inventory.secret_name_projection(inventory)
        self.assertEqual(projection["collection_status"], "failed")
        self.assertEqual(projection["secret_scopes"][0]["coverage"], "unknown")

    @mock.patch.object(azure_inventory.shutil, "which", return_value="/usr/bin/az")
    @mock.patch.object(azure_inventory, "collect_inventory")
    def test_require_complete_returns_error_after_writing_partial_report(self, collect, _which):
        collect.return_value = {
            "schema_version": "1.0", "generated_at": "2026-08-04T12:00:00Z", "status": "complete",
            "subscription": {"id": "sub", "name": "demo", "state": "Enabled"},
            "resources": {"key_vaults": [{"name": "vault", "resourceGroup": "group"}]}, "issues": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            code = azure_inventory.main(["--output-dir", directory, "--quiet", "--require-complete"])
            self.assertEqual(code, azure_inventory.EXIT_ERROR)
            self.assertTrue((Path(directory) / "azure-secret-name-inventory.json").is_file())

    @mock.patch.object(azure_inventory.shutil, "which", return_value=None)
    def test_main_fails_cleanly_when_azure_cli_is_missing(self, _which):
        stderr = io.StringIO()
        with mock.patch("sys.stderr", stderr):
            code = azure_inventory.main(["--quiet"])

        self.assertEqual(code, azure_inventory.EXIT_ERROR)
        self.assertIn("Azure CLI executable not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
