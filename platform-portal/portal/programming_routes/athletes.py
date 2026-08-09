from datetime import UTC, datetime

from flask import Blueprint, abort, render_template

from ..extensions import db
from ..models.athlete import Athlete
from ..models.programming import TrainingBlock, TrainingSessionLog
from ..services.training_schedule import project_training_schedule
from ..services.weekly_programming_intelligence import map_athlete_programming_context


def register_athlete_routes(blueprint: Blueprint) -> None:
    @blueprint.get("/athletes/<int:athlete_id>/programming")
    def athlete_program(athlete_id: int):
        athlete = db.session.get(Athlete, athlete_id)
        if athlete is None:
            abort(404)

        blocks = (
            TrainingBlock.query.filter_by(athlete_id=athlete.id)
            .order_by(TrainingBlock.created_at.desc(), TrainingBlock.id.desc())
            .all()
        )
        current_block = next((item for item in blocks if item.status == "active"), None)
        previous_blocks = [item for item in blocks if item != current_block]
        logs = {
            item.session_id: item
            for item in TrainingSessionLog.query.filter_by(athlete_id=athlete.id).all()
            if item.session_id is not None
        }
        schedule = project_training_schedule(
            current_block, logs, today=datetime.now(UTC).date()
        )

        return render_template(
            "programming/athlete_program.html",
            athlete=athlete,
            current_block=current_block,
            previous_blocks=previous_blocks,
            current_week=schedule.current_week,
            schedule=schedule,
            athlete_context=map_athlete_programming_context(athlete),
        )

    @blueprint.get("/programming")
    def index():
        athletes = Athlete.query.order_by(Athlete.last_name.asc()).all()
        blocks = TrainingBlock.query.order_by(TrainingBlock.id.desc()).all()
        active_by_athlete = {}
        for block in blocks:
            if block.status == "active" and block.athlete_id not in active_by_athlete:
                active_by_athlete[block.athlete_id] = block
        return render_template("programming/index.html", athletes=athletes, blocks=blocks, active_by_athlete=active_by_athlete)
