from datetime import UTC, datetime

from flask import Blueprint, render_template
from sqlalchemy.orm import selectinload

from ..models.athlete import Athlete
from ..models.programming import TrainingBlock, TrainingSessionLog, TrainingWeek
from ..services.training_schedule import local_today, project_training_schedule
from ..services.weekly_programming_intelligence import map_athlete_programming_context
from ..tenancy import athlete_query_for_request, require_athlete_access


def register_athlete_routes(blueprint: Blueprint) -> None:
    @blueprint.get("/athletes/<int:athlete_id>/programming")
    def athlete_program(athlete_id: int):
        athlete = require_athlete_access(athlete_id)

        blocks = (
            TrainingBlock.query.options(
                selectinload(TrainingBlock.weeks).selectinload(TrainingWeek.sessions)
            )
            .filter_by(athlete_id=athlete.id)
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
            current_block, logs,
            today=local_today(current_block.timezone) if current_block else datetime.now(UTC).date(),
        )

        return render_template(
            "programming/athlete_program.html",
            athlete=athlete,
            current_block=current_block,
            previous_blocks=previous_blocks,
            current_week=schedule.current_week,
            schedule=schedule,
            athlete_context=map_athlete_programming_context(athlete),
            workspace_athletes=athlete_query_for_request().order_by(Athlete.last_name.asc()).all(),
        )

    @blueprint.get("/programming")
    def index():
        athletes = athlete_query_for_request().order_by(Athlete.last_name.asc()).all()
        athlete_ids = [athlete.id for athlete in athletes]
        blocks = (
            TrainingBlock.query.filter(TrainingBlock.athlete_id.in_(athlete_ids))
            .order_by(TrainingBlock.id.desc())
            .all()
        )
        active_by_athlete = {}
        for block in blocks:
            if block.status == "active" and block.athlete_id not in active_by_athlete:
                active_by_athlete[block.athlete_id] = block
        return render_template("programming/index.html", athletes=athletes, blocks=blocks, active_by_athlete=active_by_athlete)
