from flask import Blueprint, jsonify

from ..services.history import HistoryService

history_bp = Blueprint("history_api", __name__)
service = HistoryService()


@history_bp.get("/history")
def list_history():
    return jsonify({"items": service.get_all()})
