from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from .api.health import health_bp
from .api.platform import platform_bp
from .extensions import db
from .views import views_bp


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )

    portal_root = Path(__file__).resolve().parents[1]
    default_database = portal_root / "data" / "platform-history.db"

    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.getenv(
            "DATABASE_URL",
            f"sqlite:///{default_database}",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config:
        app.config.update(test_config)

    default_database.parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(platform_bp, url_prefix="/api/v1")
    app.register_blueprint(views_bp)

    with app.app_context():
        from .models.platform_snapshot import PlatformSnapshot

        _ = PlatformSnapshot
        db.create_all()

    return app
