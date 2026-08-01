from flask import Blueprint, jsonify, request

from ..services.recommendations import RecommendationService

recommendations_bp = Blueprint("recommendations_api", __name__)
service = RecommendationService()


def positive_int(value: str | None, default: int, maximum: int) -> int:
    try:
        parsed = int(value) if value is not None else default
    except ValueError:
        return default
    return max(1, min(parsed, maximum))


@recommendations_bp.get("/recommendations")
def recommendations():
    hours = positive_int(request.args.get("hours"), 24, 2160)
    return jsonify(service.generate(hours=hours))
