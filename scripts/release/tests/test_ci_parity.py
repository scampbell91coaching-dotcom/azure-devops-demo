import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[3]
PORTAL_WORKFLOWS = (
    ROOT / ".github/workflows/app-deploy.yml",
    ROOT / ".github/workflows/browser-tests.yml",
    ROOT / ".github/workflows/private-platform-deploy.yml",
)


class CIParityContractTests(unittest.TestCase):
    def test_portal_workflows_use_repository_python_pin(self):
        expected = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
        self.assertRegex(expected, r"^3\.12\.\d+$")

        for workflow in PORTAL_WORKFLOWS:
            with self.subTest(workflow=workflow.name):
                content = workflow.read_text(encoding="utf-8")
                self.assertIn('python-version-file: ".python-version"', content)
                self.assertIsNone(re.search(r'python-version:\s*["\']?3\.12', content))

    def test_browser_workflows_install_chromium_with_system_dependencies(self):
        for relative in (
            ".github/workflows/browser-tests.yml",
            ".github/workflows/private-platform-deploy.yml",
        ):
            with self.subTest(workflow=relative):
                content = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("npx playwright install --with-deps chromium", content)
                self.assertIn('E2E_TEST_ONLY: "1"', content)

    def test_browser_failure_artifact_matches_playwright_output(self):
        config = (ROOT / "playwright.config.ts").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/browser-tests.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("outputDir: '.tmp/playwright-test-results'", config)
        self.assertIn(".tmp/playwright-test-results/", workflow)

    def test_release_evidence_pins_canonical_alembic_head(self):
        implementation = (ROOT / "scripts/release/release_evidence.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'EXPECTED_ALEMBIC_HEAD = "0026_programming_exposure_roles"',
            implementation,
        )


if __name__ == "__main__":
    unittest.main()
