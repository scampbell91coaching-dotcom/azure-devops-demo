"""Start the portal against a fresh, deterministic E2E-only SQLite database."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "platform-portal"
DATABASE = ROOT / ".tmp" / "traditional-strength-e2e.sqlite"

sys.path.insert(0, str(PORTAL))
DATABASE.parent.mkdir(exist_ok=True)
DATABASE.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{DATABASE}"

from flask import abort, jsonify, session  # noqa: E402
from portal import create_app  # noqa: E402
from portal.extensions import db  # noqa: E402
from portal.models.athlete import Athlete  # noqa: E402
from seed_database import seed_database  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()

    app = create_app(
        {
            "TESTING": True,
            "AUTHENTICATION_DISABLED": True,
            "SECRET_KEY": "e2e-placeholder-only",
        }
    )
    seed_database(app)

    @app.post("/__e2e__/athlete-session/<int:athlete_id>")
    def select_e2e_athlete(athlete_id: int):
        """Test-only session selection; this is not an authentication flow."""
        if not app.testing:
            abort(404)
        if db.session.get(Athlete, athlete_id) is None:
            abort(404)
        session.clear()
        session["athlete_id"] = athlete_id
        return jsonify({"athlete_id": athlete_id})

    app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
