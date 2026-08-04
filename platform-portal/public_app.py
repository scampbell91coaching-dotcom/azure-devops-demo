from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify

from portal.coaching_applications import coaching_applications_bp
from portal.database_config import resolve_database_uri
from portal.extensions import db
from portal.lead_magnets import lead_magnets_bp
from portal.security import init_security_headers


def create_public_app(
    test_config: dict[str, object] | None = None,
) -> Flask:
    root = Path(__file__).resolve().parent

    app = Flask(
        __name__,
        template_folder=str(root / "templates"),
        static_folder=str(root / "static"),
        static_url_path="/lead-static",
    )
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=resolve_database_uri(
            application_root=root,
            local_filename="public-leads.db",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=64 * 1024,
    )

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    init_security_headers(app)

    app.register_blueprint(lead_magnets_bp)
    app.register_blueprint(coaching_applications_bp)

    @app.get("/health")
    def health():
        return jsonify({"status": "healthy"})

    with app.app_context():
        from portal.models.lead_capture import LeadCapture

        _ = LeadCapture
        db.create_all()

    return app


app = create_public_app()
