from flask import Blueprint, jsonify, request

from ..services.executive_dashboard import ExecutiveDashboardService

executive_bp = Blueprint("executive_api", __name__)
service = ExecutiveDashboardService()


def positive_int(value: str | None, default: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        return default
    return max(1, min(parsed, maximum))


@executive_bp.get("/executive")
def executive_dashboard():
    hours = positive_int(request.args.get("hours"), 24, 2160)
    return jsonify(service.build(hours=hours))
