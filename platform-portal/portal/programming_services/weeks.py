from typing import cast

from ..extensions import db
from ..models.programming import TrainingBlock, TrainingSession, TrainingWeek
from .prescriptions import copy as copy_prescriptions


def create(
    block: TrainingBlock,
    *,
    name: str,
    notes: str | None,
) -> TrainingWeek:
    position = len(block.weeks) + 1
    week = TrainingWeek(
        block=block,
        name=name or f"Week {position}",
        position=position,
        notes=notes,
    )
    db.session.add(week)
    db.session.commit()
    return week


def duplicate(source: TrainingWeek) -> TrainingWeek:
    target = TrainingWeek(
        block=source.block,
        name=f"{source.name} Copy",
        position=len(source.block.weeks) + 1,
        notes=source.notes,
    )
    db.session.add(target)
    db.session.flush()
    for source_session in cast(list[TrainingSession], source.sessions):
        target_session = TrainingSession(
            week=target,
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
