import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "release_evidence.py"
SPEC = importlib.util.spec_from_file_location("release_evidence", MODULE_PATH)
release_evidence = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = release_evidence
SPEC.loader.exec_module(release_evidence)


class ReleaseEvidenceTests(unittest.TestCase):
    def test_sanitize_redacts_database_password_and_token(self):
        value = "postgresql://user:hunter2@db/test token=abc123"
        clean = release_evidence.sanitize(value)
        self.assertNotIn("hunter2", clean)
        self.assertNotIn("abc123", clean)
        self.assertIn("[REDACTED]", clean)

    @mock.patch.object(release_evidence.shutil, "which", return_value=None)
    def test_missing_mandatory_tool_fails_closed(self, _which):
        result = release_evidence.run_command("helm", ["helm", "version"], Path("."))
        self.assertEqual(result.status, "fail")
        self.assertTrue(result.mandatory)

    @mock.patch.object(release_evidence.shutil, "which", return_value=None)
    def test_missing_optional_tool_is_skipped(self, _which):
        result = release_evidence.run_command("optional", ["tool"], Path("."), mandatory=False)
        self.assertEqual(result.status, "skipped")

    def test_document_check_lists_missing_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            result = release_evidence.document_check(Path(directory), ["missing.md"])
        self.assertEqual(result.status, "fail")
        self.assertEqual(result.output, "missing.md")

    @mock.patch.object(release_evidence, "run_command")
    def test_multiple_migration_heads_fail(self, run_command):
        run_command.return_value = release_evidence.Check(
            "migration_heads", "pass", True, "ok", output="0001 (head)\n0002 (head)"
        )
        result = release_evidence.migration_heads_check(Path("."), "python3")
        self.assertEqual(result.status, "fail")
        self.assertIn("exactly one", result.summary)

    @mock.patch.object(release_evidence, "run_command")
    def test_unexpected_single_migration_head_fails(self, run_command):
        run_command.return_value = release_evidence.Check(
            "migration_heads", "pass", True, "ok", output="0021_saas_billing_foundation (head)"
        )
        result = release_evidence.migration_heads_check(Path("."), "python3")
        self.assertEqual(result.status, "fail")
        self.assertIn("expected migration head", result.summary)

    def test_markdown_contains_machine_status_and_checks(self):
        evidence = {
            "status": "ready", "generated_at": "2026-01-01T00:00:00Z",
            "repository": {"branch": "main", "commit": "abc", "dirty": False},
            "checks": [{"name": "pytest", "mandatory": True, "status": "pass", "summary": "ok"}],
        }
        report = release_evidence.render_markdown(evidence)
        self.assertIn("**READY**", report)
        self.assertIn("`pytest`", report)

    @mock.patch.object(release_evidence, "find_merge_markers", return_value=release_evidence.Check("markers", "pass", True, "ok"))
    @mock.patch.object(release_evidence, "document_check", return_value=release_evidence.Check("docs", "pass", True, "ok"))
    @mock.patch.object(release_evidence, "run_command")
    @mock.patch.object(release_evidence, "git_value")
    def test_main_writes_both_reports_and_returns_failure(self, git_value, run_command, _docs, _markers):
        git_value.side_effect = ["feature/test", "a" * 40, ""]
        run_command.side_effect = lambda name, command, cwd, mandatory=True: release_evidence.Check(
            name, "fail" if name == "pytest" else "pass", mandatory, "result"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / "platform-portal").mkdir()
            output = root / "reports"
            with mock.patch.dict(release_evidence.os.environ, {}, clear=True):
                code = release_evidence.main(["--repo-root", str(root), "--output-dir", str(output), "--quiet"])
            payload = json.loads((output / "release-evidence.json").read_text())
            self.assertEqual(code, release_evidence.EXIT_NOT_READY)
            self.assertEqual(payload["status"], "not_ready")
            self.assertTrue((output / "release-report.md").is_file())


if __name__ == "__main__":
    unittest.main()
