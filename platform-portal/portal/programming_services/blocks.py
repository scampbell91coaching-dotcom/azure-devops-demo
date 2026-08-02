from typing import cast

from ..extensions import db
from ..models.athlete import Athlete
from ..models.programming import TrainingBlock, TrainingSession, TrainingWeek
from .prescriptions import copy as copy_prescriptions


def create(
    athlete: Athlete,
    *,
    name: str,
    objective: str | None,
) -> TrainingBlock:
    block = TrainingBlock(athlete=athlete, name=name, objective=objective)
    db.session.add(block)
    db.session.commit()
    return block


def duplicate(source: TrainingBlock) -> TrainingBlock:
    target = TrainingBlock(
        athlete=source.athlete,
        name=f"{source.name} Copy",
        objective=source.objective,
        status="draft",
    )
    db.session.add(target)
    db.session.flush()

    for source_week in cast(list[TrainingWeek], source.weeks):
        target_week = TrainingWeek(
            block=target,
            name=source_week.name,
            position=source_week.position,
            notes=source_week.notes,
        )
        db.session.add(target_week)
        db.session.flush()
        for source_session in cast(list[TrainingSession], source_week.sessions):
            target_session = TrainingSession(
                week=target_week,
                name=source_session.name,
                day_label=source_session.day_label,
                position=source_session.position,
                notes=source_session.notes,
            )
            db.session.add(target_session)
            db.session.flush()
            copy_prescriptions(source_session, target_session)

    db.session.commit()
    return target


def archive(block: TrainingBlock) -> None:
    block.status = "archived"
    db.session.commit()


def delete_draft(block: TrainingBlock) -> int:
    athlete_id = block.athlete_id
    db.session.delete(block)
    db.session.commit()
    return athlete_id
