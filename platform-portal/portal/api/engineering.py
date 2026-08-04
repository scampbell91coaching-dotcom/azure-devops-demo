from flask import Blueprint, current_app, jsonify

from ..services.engineering_overview import EngineeringOverviewService

engineering_bp = Blueprint("engineering_api", __name__)


def build_engineering_overview():
    return EngineeringOverviewService(
        release_evidence_service=current_app.extensions["release_evidence"]
    ).build()


@engineering_bp.get("/engineering-overview")
def engineering_overview():
    return jsonify(build_engineering_overview())
