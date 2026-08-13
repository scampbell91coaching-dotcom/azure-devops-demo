from datetime import date, timedelta

from flask import Blueprint, abort, g, jsonify, request

from ..services.performance_charts import (
    AthletePerformanceChartService,
    PerformanceChartFilter,
)
from ..tenancy import coach_owns_athlete

athlete_performance_bp = Blueprint("athlete_performance_api", __name__)
service = AthletePerformanceChartService()


def _date_argument(name: str, default: date) -> date:
    value = request.args.get(name)
    if value is None:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        abort(400, description=f"{name} must use YYYY-MM-DD")


def _block_argument() -> int | None:
    value = request.args.get("block_id")
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        abort(400, description="block_id must be a positive integer")
    if parsed < 1:
        abort(400, description="block_id must be a positive integer")
    return parsed


@athlete_performance_bp.get("/athletes/<int:athlete_id>/performance/charts")
def charts(athlete_id: int):
    user = g.get("current_user")
    if user is None or not coach_owns_athlete(user.id, athlete_id):
        abort(404)
    end = _date_argument("to", date.today())
    default_start = date.min if end < date.min + timedelta(days=89) else end - timedelta(days=89)
    start = _date_argument("from", default_start)
    try:
        payload = service.build(
            athlete_id,
            PerformanceChartFilter(start=start, end=end, block_id=_block_argument()),
        )
    except LookupError:
        abort(404)
    except ValueError as error:
        abort(400, description=str(error))
    return jsonify(payload)
