from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify

from portal.extensions import db
from portal.lead_magnets import lead_magnets_bp


def create_public_app(
    test_config: dict[str, object] | None = None,
) -> Flask:
    root = Path(__file__).resolve().parent
    local_database = root / "data" / "public-leads.db"

    app = Flask(
        __name__,
        template_folder=str(root / "templates"),
        static_folder=str(root / "static"),
        static_url_path="/lead-static",
    )

    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "DATABASE_URL",
            f"sqlite:///{local_database}",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=64 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    local_database.parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(lead_magnets_bp)

    @app.get("/health")
    def health():
        return jsonify({"status": "healthy"})

    with app.app_context():
        from portal.models.lead_capture import LeadCapture

        _ = LeadCapture
        db.create_all()

    return app


app = create_public_app()
