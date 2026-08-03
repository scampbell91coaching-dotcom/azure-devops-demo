import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "reset_postgres.py"
SPEC = importlib.util.spec_from_file_location("reset_postgres", MODULE_PATH)
assert SPEC and SPEC.loader
reset_postgres = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reset_postgres)


class ValidateUrlTests(unittest.TestCase):
    def test_accepts_dedicated_loopback_database(self):
        target, maintenance = reset_postgres.validate_url(
            "postgresql://ts_app:secret@127.0.0.1:5432/traditional_strength_test"
        )
        self.assertIn("/traditional_strength_test", target)
        self.assertIn("/postgres", maintenance)

    def test_rejects_remote_database(self):
        with self.assertRaisesRegex(ValueError, "host must be"):
            reset_postgres.validate_url(
                "postgresql://ts_app:secret@db.example/traditional_strength_test"
            )

    def test_rejects_wrong_database_name(self):
        with self.assertRaisesRegex(ValueError, "name must be exactly"):
            reset_postgres.validate_url("postgresql://ts_app@localhost/production")

    def test_rejects_non_postgresql_url(self):
        with self.assertRaisesRegex(ValueError, "PostgreSQL URL"):
            reset_postgres.validate_url("sqlite:///traditional_strength_test")


if __name__ == "__main__":
    unittest.main()
