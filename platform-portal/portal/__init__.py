from flask import Flask

from .api.health import health_bp
from .api.platform import platform_bp
from .views import views_bp


def create_app() -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    app.register_blueprint(health_bp)
    app.register_blueprint(platform_bp, url_prefix="/api/v1")
    app.register_blueprint(views_bp)
    return app
