"""Run the disposable, loopback-only Traditional Strength E2E server."""

from __future__ import annotations

import argparse
import atexit
import hmac
import os
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORTAL = ROOT / "platform-portal"

sys.path.insert(0, str(PORTAL))

from security import create_disposable_database, require_test_only_environment  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8091)
    args = parser.parse_args()

    run_token = require_test_only_environment()
    database = create_disposable_database(ROOT / ".tmp")
    atexit.register(database.unlink, missing_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite:///{database}"

    from flask import abort, jsonify, request, session
    from portal import create_app
    from portal.extensions import db
    from portal.models.athlete import Athlete
    from seed_database import seed_database

    def stop_for_cleanup(_signum, _frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop_for_cleanup)
    signal.signal(signal.SIGINT, stop_for_cleanup)

    try:
        app = create_app(
            {
                "TESTING": True,
                "AUTHENTICATION_DISABLED": True,
                "LEGACY_STARTUP_INITIALIZATION": False,
                "SECRET_KEY": os.urandom(32).hex(),
            }
        )
        seed_database(app)

        print("REGISTERING __e2e__ ROUTE")

        @app.post("/__e2e__/athlete-session/<int:athlete_id>")
        def select_e2e_athlete(athlete_id: int):
            print("E2E ROUTE HIT", athlete_id)
            """Select an identity only for this token-protected local test run."""
            supplied_token = request.headers.get("X-E2E-Run-Token", "")

            if not hmac.compare_digest(supplied_token, run_token):
                return jsonify(
                    {
                        "error": "token_mismatch",
                        "supplied_length": len(supplied_token),
                        "expected_length": len(run_token),
                    }
                ), 401

            athlete = db.session.get(Athlete, athlete_id)
            if athlete is None:
                available_ids = [
                    value
                    for value, in db.session.query(Athlete.id).order_by(Athlete.id).all()
                ]
                return jsonify(
                    {
                        "error": "athlete_missing",
                        "requested_id": athlete_id,
                        "available_ids": available_ids,
                    }
                ), 404

            session.clear()
            session["athlete_id"] = athlete_id
            return jsonify({"athlete_id": athlete_id})

        app.run(
            host="127.0.0.1",
            port=args.port,
            debug=False,
            use_reloader=False,
        )
    finally:
        database.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
