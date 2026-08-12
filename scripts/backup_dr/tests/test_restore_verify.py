from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).parents[1] / "restore_verify.py"
SPEC = importlib.util.spec_from_file_location("restore_verify", MODULE_PATH)
assert SPEC and SPEC.loader
verify = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verify
SPEC.loader.exec_module(verify)


class Cursor:
    def __init__(self):
        self.rows = []

    def execute(self, sql, params=()):
        if sql == "SHOW transaction_read_only":
            self.rows = [("on",)]
        elif "count(*) FROM alembic_version" in sql:
            self.rows = [(1,)]
        elif "SELECT version_num" in sql:
            self.rows = [("0020_head",)]
        elif "information_schema.tables" in sql:
            self.rows = [(name,) for name in params[0]]
        elif "pg_constraint" in sql:
            self.rows = [(0,)]
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows


class RestoreVerifyTests(unittest.TestCase):
    def test_target_must_not_be_source(self):
        with self.assertRaisesRegex(ValueError, "must differ"):
            verify.safe_target("postgresql://u:p@prod/db", "prod", verify.CONFIRMATION)

    def test_target_requires_exact_confirmation(self):
        with self.assertRaisesRegex(ValueError, "--confirm"):
            verify.safe_target("postgresql://u:p@restore/db", "prod", "yes")

    def test_target_evidence_is_sanitised_fingerprint(self):
        host, fingerprint = verify.safe_target("postgresql://secret:password@restore/db", "prod", verify.CONFIRMATION)
        self.assertEqual(host, "restore")
        self.assertEqual(len(fingerprint), 12)
        self.assertNotIn("secret", fingerprint)
        self.assertNotIn("password", fingerprint)

    def test_checks_cover_read_only_schema_and_constraints(self):
        checks = verify.run_checks(Cursor(), "0020_head", verify.DEFAULT_TABLES)
        self.assertTrue(all(check.ok for check in checks))
        self.assertEqual({check.name for check in checks}, {
            "read_only_transaction", "single_alembic_head", "expected_alembic_head",
            "critical_tables_present", "constraints_validated",
        })

    def test_script_contains_no_data_mutation_statements(self):
        source = MODULE_PATH.read_text()
        for statement in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "TRUNCATE ", "ALTER "):
            self.assertNotIn(statement, source)
        self.assertIn("SET TRANSACTION READ ONLY", source)


if __name__ == "__main__":
    unittest.main()
