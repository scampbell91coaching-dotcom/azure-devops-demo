from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL_ROOT = ROOT / "platform-portal"

sys.path.insert(0, str(PORTAL_ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:////tmp/traditional-strength-public-e2e.db",
)
os.environ.setdefault("SECRET_KEY", "public-e2e-secret")
os.environ.setdefault("FLASK_ENV", "testing")

from public_app import app  # noqa: E402


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=8092,
        debug=False,
        use_reloader=False,
    )
