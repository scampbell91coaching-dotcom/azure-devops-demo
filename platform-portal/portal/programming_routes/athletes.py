from flask import Blueprint, abort, render_template

from ..extensions import db
from ..models.athlete import Athlete
from ..models.programming import TrainingBlock


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
        current_block = next(
            (item for item in blocks if item.status != "archived"),
            None,
        )
        previous_blocks = [item for item in blocks if item != current_block]

        return render_template(
            "programming/athlete_program.html",
            athlete=athlete,
            current_block=current_block,
            previous_blocks=previous_blocks,
        )

    @blueprint.get("/programming")
    def index():
        athletes = Athlete.query.order_by(Athlete.last_name.asc()).all()
        blocks = TrainingBlock.query.order_by(TrainingBlock.id.desc()).all()
        return render_template(
            "programming/index.html", athletes=athletes, blocks=blocks
        )
