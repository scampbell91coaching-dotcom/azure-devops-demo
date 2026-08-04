import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "credential_audit.py"
SPEC = importlib.util.spec_from_file_location("credential_audit", MODULE_PATH)
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


def credential(**overrides):
    item = {
        "name": "ci-identity",
        "owner": "Platform",
        "last_verified": "2026-07-01",
        "storage_location": "github-actions:repository:CLIENT_ID",
        "rotation_status": "current",
    }
    item.update(overrides)
    return item


def github_inventory(names=("CLIENT_ID",)):
    return {
        "schema_version": "1.0", "source": "github", "generated_at": "2026-08-04T12:00:00Z",
        "collection_status": "complete", "secret_scopes": [{
            "scope": {"repository": "acme/widgets", "environment": None, "subscription": None, "resource_group": None, "key_vault": None},
            "coverage": "complete", "secret_names": list(names),
        }],
    }


class CredentialAuditTests(unittest.TestCase):
    def test_classifies_coverage_and_independent_findings(self):
        items = [
            credential(),
            credential(name="missing", storage_location="github-actions:repository:NOT_THERE", rotation_status="required"),
            credential(name="unknown", storage_location="ssh-agent:laptop:key", last_verified="2025-01-01"),
        ]
        report = audit_module.audit(
            items,
            {"github": audit_module.parse_github_inventory(github_inventory()), "azure": None},
            date(2026, 8, 4),
            90,
        )
        self.assertEqual([item["coverage"] for item in report["credentials"]], ["present", "missing", "unknown"])
        self.assertEqual(report["summary"], {"present": 1, "missing": 1, "unknown": 1, "stale": 1, "rotation-required": 1})

    def test_missing_optional_inventory_is_unknown_not_missing(self):
        report = audit_module.audit([credential()], {"github": None, "azure": None}, date(2026, 8, 4), 90)
        self.assertEqual(report["credentials"][0]["coverage"], "unknown")

    def test_date_boundary_and_future_date_are_handled(self):
        items = [
            credential(name="boundary", last_verified="2026-05-06"),
            credential(name="old", last_verified="2026-05-05"),
            credential(name="future", last_verified="2026-08-05"),
        ]
        report = audit_module.audit(items, {"github": audit_module.parse_github_inventory(github_inventory(())), "azure": None}, date(2026, 8, 4), 90)
        self.assertEqual([item["stale"] for item in report["credentials"]], [False, True, True])
        with self.assertRaisesRegex(audit_module.AuditError, "valid YYYY-MM-DD"):
            audit_module.parse_manifest({"schema_version": "1.0", "credentials": [credential(last_verified="2026-02-30")]})

    def test_inventory_parser_constructs_canonical_location(self):
        parsed = audit_module.parse_github_inventory(github_inventory())
        self.assertEqual(parsed["secret_scopes"][0]["secret_names"], ["CLIENT_ID"])

    def test_rejects_value_fields_without_echoing_value(self):
        marker = "DO-NOT-LEAK-THIS"
        with self.assertRaises(audit_module.AuditError) as caught:
            document = github_inventory()
            document["secret_scopes"][0]["value"] = marker
            audit_module.parse_github_inventory(document)
        self.assertNotIn(marker, str(caught.exception))

    def test_cli_writes_both_reports_and_failure_is_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": "1.0", "credentials": [credential()]}), encoding="utf-8")
            output = root / "output"
            command = [sys.executable, str(MODULE_PATH), "--manifest", str(manifest), "--output-dir", str(output), "--as-of", "2026-08-04"]
            result = subprocess.run(
                command, capture_output=True, text=True, check=False,
                preexec_fn=lambda: os.umask(0o022),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / "credential-audit.json").is_file())
            self.assertTrue((output / "credential-audit.md").is_file())
            self.assertEqual(output.stat().st_mode & 0o777, 0o700)
            self.assertEqual((output / "credential-audit.json").stat().st_mode & 0o777, 0o600)
            self.assertEqual((output / "credential-audit.md").stat().st_mode & 0o777, 0o600)

            marker = "DO-NOT-LEAK-THIS"
            manifest.write_text(json.dumps({"schema_version": "1.0", "credentials": [], "token": marker}), encoding="utf-8")
            failed = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(failed.returncode, 2)
            self.assertNotIn(marker, failed.stdout + failed.stderr)

    def test_cli_handles_missing_malformed_and_unwritable_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing.json"
            command = [sys.executable, str(MODULE_PATH), "--manifest", str(missing)]
            failed = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("cannot read input file", failed.stderr)

            malformed = root / "malformed.json"
            marker = "DO-NOT-LEAK-THIS"
            malformed.write_text('{"token":"' + marker, encoding="utf-8")
            failed = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--manifest", str(malformed)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(failed.returncode, 2)
            self.assertIn("not valid UTF-8 JSON", failed.stderr)
            self.assertNotIn(marker, failed.stdout + failed.stderr)

            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps({"schema_version": "1.0", "credentials": [credential()]}),
                encoding="utf-8",
            )
            output_file = root / "not-a-directory"
            output_file.write_text("occupied", encoding="utf-8")
            failed = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--manifest",
                    str(manifest),
                    "--output-dir",
                    str(output_file),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(failed.returncode, 2)
            self.assertIn("cannot write credential audit reports", failed.stderr)
            self.assertNotIn("Traceback", failed.stderr)


if __name__ == "__main__":
    unittest.main()
