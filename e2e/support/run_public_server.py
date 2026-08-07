from __future__ import annotations

import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL_ROOT = ROOT / "platform-portal"

sys.path.insert(0, str(PORTAL_ROOT))
sys.path.insert(0, str(ROOT / "e2e" / "support"))

from security import require_test_only_environment  # noqa: E402

require_test_only_environment()

database = Path(os.environ["E2E_DATABASE_PATH"]).resolve()
allowed_root = (ROOT / ".tmp").resolve()
if allowed_root not in database.parents:
    raise RuntimeError("E2E_DATABASE_PATH must be inside the repository .tmp directory")

os.environ["DATABASE_URL"] = f"sqlite:///{database}"
os.environ.setdefault("SECRET_KEY", "public-e2e-secret")
os.environ.setdefault("FLASK_ENV", "testing")

# The private server owns disposable database creation and deterministic
# seeding. Wait for that initialization before the public Flask app runs its
# idempotent create_all, avoiding concurrent SQLite DDL during parallel server
# startup.
deadline = time.monotonic() + 90
while time.monotonic() < deadline:
    try:
        with sqlite3.connect(database) as connection:
            seeded = connection.execute(
                "SELECT COUNT(*) FROM users WHERE email = ?",
                ("coach.e2e@example.test",),
            ).fetchone()[0]
        if seeded:
            break
    except sqlite3.Error:
        pass
    time.sleep(0.1)
else:
    raise RuntimeError("private E2E database initialization timed out")

from public_app import app  # noqa: E402


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=8092,
        debug=False,
        use_reloader=False,
    )
