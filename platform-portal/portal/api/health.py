from flask import Blueprint, jsonify
from sqlalchemy import text

from ..extensions import db
from ..observability import set_dependency_available

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    """Stable, dependency-free compatibility endpoint for existing consumers."""
    return jsonify({"status": "healthy"}), 200


@health_bp.get("/live")
def live():
    """Process-only liveness signal; dependency outages must not cause restarts."""
    return jsonify({"status": "alive"}), 200


@health_bp.get("/ready")
def ready():
    """Traffic readiness, including a bounded database round trip."""
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - readiness converts dependency errors to 503.
        db.session.rollback()
        set_dependency_available("database", False)
        return jsonify(
            {"status": "not_ready", "checks": {"database": "unavailable"}}
        ), 503
    set_dependency_available("database", True)
    return jsonify({"status": "ready", "checks": {"database": "available"}}), 200
