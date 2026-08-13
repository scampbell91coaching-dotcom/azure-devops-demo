import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "docs" / "release" / "pl-regression-matrix.md"
EXPECTED_SMOKE_ORDER = (
    "e2e/tests/auth.spec.ts",
    "e2e/tests/coach.spec.ts",
    "e2e/tests/athlete-training.spec.ts",
    "e2e/tests/meal-plan.spec.ts",
    "e2e/tests/performance-dashboard.spec.ts",
    "e2e/tests/observability.spec.ts",
    "e2e/tests/mobile.spec.ts",
)


class PowerliftingRegressionMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = MATRIX.read_text(encoding="utf-8")

    def test_every_referenced_test_file_exists(self):
        references = set(re.findall(
            r"`((?:e2e/tests|platform-portal/tests|scripts/(?:release|migrations|gitops)/tests|tests)/[^`]+\.(?:py|ts))`",
            self.text,
        ))
        self.assertGreaterEqual(len(references), 50)
        self.assertEqual(
            sorted(path for path in references if not (ROOT / path).is_file()), []
        )

    def test_smoke_order_is_explicit_and_stable(self):
        section = self.text.split("## Ordered Playwright smoke", 1)[1]
        actual = tuple(re.findall(
            r"^\d+\. `(e2e/tests/[^`]+\.spec\.ts)`", section, re.MULTILINE
        ))
        self.assertEqual(actual, EXPECTED_SMOKE_ORDER)

    def test_future_tenancy_spec_is_not_release_evidence(self):
        self.assertIn("saas-tenancy.future.spec.ts", self.text)
        self.assertIn("not green release evidence", self.text)


if __name__ == "__main__":
    unittest.main()
