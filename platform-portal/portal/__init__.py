from __future__ import annotations

from pathlib import Path

from flask import Flask

from .api.executive import executive_bp
from .api.health import health_bp
from .api.history import history_bp
from .api.platform import platform_bp
from .api.recommendations import recommendations_bp
from .athletes import athletes_bp
from .database_config import resolve_database_uri
from .extensions import db
from .lead_magnets import lead_magnets_bp
from .programming import programming_bp
from .programming_pack2 import programming_pack2_bp
from .views import views_bp


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    portal_root = Path(__file__).resolve().parents[1]

    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=resolve_database_uri(
            application_root=portal_root,
            local_filename="platform-history.db",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    if test_config:
        app.config.update(test_config)
    db.init_app(app)

    app.register_blueprint(health_bp)
    app.register_blueprint(executive_bp, url_prefix="/api/v1")
    app.register_blueprint(history_bp, url_prefix="/api/v1")
    app.register_blueprint(platform_bp, url_prefix="/api/v1")
    app.register_blueprint(recommendations_bp, url_prefix="/api/v1")
    app.register_blueprint(views_bp)
    app.register_blueprint(lead_magnets_bp)
    app.register_blueprint(programming_bp)
    app.register_blueprint(programming_pack2_bp)
    app.register_blueprint(athletes_bp)

    with app.app_context():
        from .models.athlete import Athlete
        from .models.lead_capture import LeadCapture
        from .models.nutrition_checkin import NutritionCheckIn
        from .models.platform_snapshot import PlatformSnapshot
        from .models.programming import (
            ExercisePrescription,
            TrainingBlock,
            TrainingSession,
            TrainingWeek,
        )

        _ = PlatformSnapshot
        _ = LeadCapture
        _ = TrainingBlock
        _ = TrainingWeek
        _ = TrainingSession
        _ = ExercisePrescription
        _ = Athlete
        _ = NutritionCheckIn
        db.create_all()

    return app
