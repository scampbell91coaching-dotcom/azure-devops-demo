from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

PATH = Path(__file__).parents[1] / "restore_preflight.py"
SPEC = importlib.util.spec_from_file_location("restore_preflight", PATH)
assert SPEC and SPEC.loader
preflight = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = preflight
SPEC.loader.exec_module(preflight)


class PreflightTests(unittest.TestCase):
    def test_disposable_target_passes(self):
        checks = preflight.validate("/servers/ts-prod", "/servers/ts-restore-drill", "prod.db", "restore-drill.db")
        self.assertTrue(all(item["ok"] for item in checks))

    def test_equal_target_fails(self):
        checks = preflight.validate("/servers/a", "/servers/a", "a.db", "a.db")
        self.assertFalse(all(item["ok"] for item in checks))

    def test_production_like_target_fails_even_if_restore_named(self):
        checks = preflight.validate("/servers/source", "/servers/prod-restore", "source.db", "prod-restore.db")
        self.assertFalse(next(item for item in checks if item["name"] == "target_not_production_named")["ok"])

    def test_utc_requires_offset(self):
        with self.assertRaisesRegex(ValueError, "UTC offset"):
            preflight.utc("2026-08-18T01:00:00")


if __name__ == "__main__": unittest.main()
