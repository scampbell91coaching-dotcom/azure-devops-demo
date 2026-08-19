from __future__ import annotations

import importlib.util
import hashlib
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
    def __init__(self, pdf_rows=None):
        self.rows = []
        self.pdf_rows = pdf_rows if pdf_rows is not None else [
            (b"%PDF-valid", hashlib.sha256(b"%PDF-valid").hexdigest(), 10),
        ]

    def execute(self, sql, params=()):
        compact = " ".join(sql.split())
        if sql == "SHOW transaction_read_only": self.rows = [("on",)]
        elif "count(*) FROM alembic_version" in sql: self.rows = [(1,)]
        elif "SELECT version_num" in sql: self.rows = [("0026_programming_exposure_roles",)]
        elif "information_schema.tables" in sql: self.rows = [(name,) for name in params[0]]
        elif compact.startswith('SELECT count(*) FROM "'): self.rows = [(4,)]
        elif "pg_constraint" in sql: self.rows = [(0,)]
        elif "pg_index" in sql: self.rows = [(0,)]
        elif "FROM coach_athlete_ownerships o" in sql: self.rows = [(0,)]
        elif "FROM pdf_meal_plans p" in sql: self.rows = [(0,)]
        elif "FROM pg_sequences" in sql: self.rows = [(0,)]
        elif sql == "SELECT pdf_bytes, content_sha256, content_length FROM pdf_meal_plans":
            self.rows = list(self.pdf_rows)
        else: raise AssertionError(sql)

    def fetchone(self): return self.rows[0]
    def fetchall(self): return self.rows
    def fetchmany(self, size):
        result, self.rows = self.rows[:size], self.rows[size:]
        return result


class RestoreVerifyTests(unittest.TestCase):
    def test_target_must_not_be_source(self):
        with self.assertRaisesRegex(ValueError, "must differ"):
            verify.safe_target("postgresql://u:p@db.example/db_restore", "db.example", verify.CONFIRMATION)

    def test_target_requires_disposable_name(self):
        with self.assertRaisesRegex(ValueError, "explicitly named"):
            verify.safe_target("postgresql://u:p@temporary.example/db", "source.example", verify.CONFIRMATION)

    def test_target_rejects_production_like_name(self):
        with self.assertRaisesRegex(ValueError, "resembles production"):
            verify.safe_target("postgresql://u:p@prod-restore.example/db", "source.example", verify.CONFIRMATION)

    def test_target_evidence_is_sanitised(self):
        host, fingerprint = verify.safe_target("postgresql://secret:password@restore.example/drill_db", "source.example", verify.CONFIRMATION)
        self.assertEqual(host, "restore.example")
        self.assertEqual(len(fingerprint), 12)
        self.assertNotIn("secret", fingerprint)

    def test_minimum_counts_are_strictly_parsed(self):
        self.assertEqual(verify.parse_minimum_counts(["athletes=3"])["athletes"], 3)
        with self.assertRaises(ValueError): verify.parse_minimum_counts(["athletes;drop=1"])
        with self.assertRaises(ValueError): verify.parse_minimum_counts(["athletes=-1"])

    def test_checks_cover_restore_invariants(self):
        checks = verify.run_checks(Cursor(), "0026_programming_exposure_roles", {table: 1 for table in verify.DEFAULT_TABLES})
        self.assertTrue(all(check.ok for check in checks))
        names = {check.name for check in checks}
        for expected in ("constraints_validated", "indexes_valid_and_ready", "tenant_ownership_consistent", "sequences_not_behind", "pdf_metadata", "pdf_content_sha256"):
            self.assertIn(expected, names)

    def test_valid_pdf_payload_passes_python_sha256_verification(self):
        payload = b"%PDF-1.4\nvalid restored payload\n%%EOF\n"
        metadata_bad, hashes_bad = verify.verify_pdf_content(Cursor([
            (payload, hashlib.sha256(payload).hexdigest(), len(payload)),
        ]))
        self.assertEqual((metadata_bad, hashes_bad), (0, 0))

    def test_corrupted_pdf_payload_fails_python_sha256_verification(self):
        original = b"%PDF-1.4\noriginal restored payload\n%%EOF\n"
        corrupted = original.replace(b"original", b"corrupted")
        metadata_bad, hashes_bad = verify.verify_pdf_content(Cursor([
            (corrupted, hashlib.sha256(original).hexdigest(), len(corrupted)),
        ]))
        self.assertEqual(metadata_bad, 0)
        self.assertEqual(hashes_bad, 1)

    def test_pdf_byte_length_mismatch_fails_metadata_verification(self):
        payload = b"%PDF-1.4\nrestored payload\n%%EOF\n"
        metadata_bad, hashes_bad = verify.verify_pdf_content(Cursor([
            (payload, hashlib.sha256(payload).hexdigest(), len(payload) + 1),
        ]))
        self.assertEqual(metadata_bad, 1)
        self.assertEqual(hashes_bad, 0)

    def test_expected_pdf_table_absence_fails_pdf_checks(self):
        cursor = Cursor()
        original_execute = cursor.execute

        def execute_without_pdf_table(sql, params=()):
            original_execute(sql, params)
            if "information_schema.tables" in sql:
                cursor.rows = [(name,) for name in params[0] if name != "pdf_meal_plans"]

        cursor.execute = execute_without_pdf_table
        checks = verify.run_checks(
            cursor, "0026_programming_exposure_roles",
            {table: 1 for table in verify.DEFAULT_TABLES},
        )
        pdf_checks = {check.name: check for check in checks if check.name.startswith("pdf_")}
        self.assertFalse(pdf_checks["pdf_metadata"].ok)
        self.assertFalse(pdf_checks["pdf_content_sha256"].ok)

    def test_script_contains_no_data_mutation_statements(self):
        source = MODULE_PATH.read_text()
        for statement in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "TRUNCATE ", "ALTER "):
            self.assertNotIn(statement, source)
        self.assertIn("SET TRANSACTION READ ONLY", source)


if __name__ == "__main__": unittest.main()
