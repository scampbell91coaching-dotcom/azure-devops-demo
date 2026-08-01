from flask import Blueprint, jsonify, request

from ..services.history import HistoryService

history_bp = Blueprint("history_api", __name__)
service = HistoryService()


def positive_int(value: str | None, default: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        return default
    return max(1, min(parsed, maximum))


@history_bp.get("/history")
def history():
    limit = positive_int(request.args.get("limit"), 288, 5000)
    return jsonify({"items": service.recent(limit=limit), "limit": limit})


@history_bp.get("/history/chart")
def history_chart():
    hours = positive_int(request.args.get("hours"), 24, 2160)
    return jsonify({"hours": hours, **service.chart(hours=hours)})
