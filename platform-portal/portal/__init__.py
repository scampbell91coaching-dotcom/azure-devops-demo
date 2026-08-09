from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from flask import Flask, g, render_template

from .api.engineering import engineering_bp
from .api.executive import executive_bp
from .api.health import health_bp
from .api.history import history_bp
from .api.platform import platform_bp
from .api.recommendations import recommendations_bp
from .athletes import athletes_bp
from .attempt_selection import attempt_selection_bp
from .auth import init_auth
from .block_factory import block_factory_bp
from .checkins import checkins_bp
from .coach_dashboard import coach_dashboard_bp
from .coach_applications import coach_applications_bp
from .database_cli import register_database_commands
from .database_config import resolve_database_uri
from .exercise_library import exercise_library_bp
from .extensions import db, migrate
from .lead_magnets import lead_magnets_bp
from .meet_day import meet_day_bp
from .nutrition_imports import nutrition_imports_bp
from .programming import programming_bp
from .programming_engine import programming_engine_bp
from .programming_pack2 import programming_pack2_bp
from .programming_templates import programming_templates_bp
from .release_readiness import release_readiness_bp
from .security import init_security_headers
from .services.release_readiness import ReleaseEvidenceService
from .views import views_bp

TESTING_SECRET_KEY = "testing-only-secret-key"


def create_app(test_config: dict[str, object] | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    portal_root = Path(__file__).resolve().parents[1]

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=resolve_database_uri(
            application_root=portal_root,
            local_filename="platform-history.db",
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        LEGACY_STARTUP_INITIALIZATION=None,
        AUTHENTICATION_DISABLED=False,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
        LOGIN_RATE_LIMIT_ATTEMPTS=5,
        LOGIN_RATE_LIMIT_WINDOW_SECONDS=15 * 60,
        NUTRITION_UPLOAD_MAX_BYTES=10 * 1024 * 1024,
        MFP_API_ENABLED=False,
        SMTP_HOST=os.environ.get("SMTP_HOST"),
        SMTP_PORT=int(os.environ.get("SMTP_PORT", "587")),
        SMTP_USERNAME=os.environ.get("SMTP_USERNAME"),
        SMTP_PASSWORD=os.environ.get("SMTP_PASSWORD"),
        SMTP_USE_TLS=os.environ.get("SMTP_USE_TLS", "true").casefold()
        in {"1", "true", "yes"},
        ACCOUNT_PUBLIC_BASE_URL=os.environ.get("ACCOUNT_PUBLIC_BASE_URL"),
        ACCOUNT_INVITATION_LIFETIME=timedelta(hours=48),
        ACCOUNT_RESET_LIFETIME=timedelta(hours=1),
        REPOSITORY_ROOT=portal_root.parent,
        RELEASE_EVIDENCE_MAX_AGE_SECONDS=24 * 60 * 60,
    )

    if test_config:
        app.config.update(test_config)
    if (
        test_config
        and test_config.get("TESTING")
        and "AUTHENTICATION_DISABLED" not in test_config
    ):
        app.config["AUTHENTICATION_DISABLED"] = True
    if app.testing and "SESSION_COOKIE_SECURE" not in (test_config or {}):
        app.config["SESSION_COOKIE_SECURE"] = False
    if not app.config["SECRET_KEY"]:
        if app.testing:
            app.config["SECRET_KEY"] = TESTING_SECRET_KEY
        else:
            raise RuntimeError("SECRET_KEY must be set for the private portal")
    if app.config["AUTHENTICATION_DISABLED"] and not app.testing:
        raise RuntimeError("AUTHENTICATION_DISABLED is only permitted while testing")
    if app.config["LEGACY_STARTUP_INITIALIZATION"] is None:
        app.config["LEGACY_STARTUP_INITIALIZATION"] = app.testing
    db.init_app(app)
    app.extensions["release_evidence"] = ReleaseEvidenceService(
        repository_root=Path(app.config["REPOSITORY_ROOT"]),
        evidence_path=app.config.get("RELEASE_EVIDENCE_FILE"),
        max_age_seconds=int(app.config["RELEASE_EVIDENCE_MAX_AGE_SECONDS"]),
    )
    init_security_headers(app, prevent_caching=True)
    migrate.init_app(
        app,
        db,
        directory=str(portal_root / "migrations"),
    )

    # Import every coaching model once so relationships and Alembic metadata are
    # complete without coupling model registration to schema mutation.
    from . import models

    _ = models

    app.register_blueprint(health_bp)
    init_auth(app)
    app.register_blueprint(executive_bp, url_prefix="/api/v1")
    app.register_blueprint(engineering_bp, url_prefix="/api/v1")
    app.register_blueprint(history_bp, url_prefix="/api/v1")
    app.register_blueprint(platform_bp, url_prefix="/api/v1")
    app.register_blueprint(recommendations_bp, url_prefix="/api/v1")
    app.register_blueprint(views_bp)
    app.register_blueprint(release_readiness_bp)
    app.register_blueprint(lead_magnets_bp)
    app.register_blueprint(programming_bp)
    app.register_blueprint(block_factory_bp)
    app.register_blueprint(exercise_library_bp)
    app.register_blueprint(programming_engine_bp)
    app.register_blueprint(programming_pack2_bp)
    app.register_blueprint(programming_templates_bp)
    app.register_blueprint(athletes_bp)
    app.register_blueprint(attempt_selection_bp)
    app.register_blueprint(checkins_bp)
    app.register_blueprint(coach_dashboard_bp)
    app.register_blueprint(coach_applications_bp)
    app.register_blueprint(meet_day_bp)
    app.register_blueprint(nutrition_imports_bp)

    if app.config["LEGACY_STARTUP_INITIALIZATION"]:
        with app.app_context():
            from .models.exercise_library import ensure_exercise_knowledge_columns
            from .models.programming import ensure_prescription_mode_columns
            from .seed_programming_engine import seed_programming_engine

            db.create_all()
            ensure_exercise_knowledge_columns()
            ensure_prescription_mode_columns()
            seed_programming_engine()

    from .services.exercise_knowledge_import import (
        register_exercise_knowledge_import_command,
    )

    register_exercise_knowledge_import_command(app)
    register_database_commands(app)

    error_copy = {
        400: ("Check your request", "Review the highlighted information and try again."),
        403: ("Access denied", "Your account does not have access to this area."),
        404: ("Page not found", "The page may have moved or no longer exists."),
        500: ("Something went wrong", "The platform could not complete that request."),
    }
    for status, (title, message) in error_copy.items():
        def render_error(error, status=status, title=title, message=message):
            description = getattr(error, "description", None)
            if status == 403:
                user = g.get("current_user")
                if user is not None and getattr(user, "role", None) == "athlete":
                    back_url = "/athlete/dashboard"
                else:
                    back_url = "/coach"
                return render_template(
                    "errors/access_denied.html", back_url=back_url
                ), status
            return render_template(
                "errors/error.html",
                status=status,
                title=title,
                message=description or message,
                back_url="/programming" if status != 403 else "/",
            ), status
        app.register_error_handler(status, render_error)

    return app
