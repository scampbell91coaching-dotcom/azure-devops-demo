from typing import cast

from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models.programming import TrainingSession, TrainingWeek
from .prescriptions import copy as copy_prescriptions
from .warmups import copy as copy_warmups


def _commit_or_rollback() -> None:
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise


def renumber(
    week: TrainingWeek,
    *,
    excluding: TrainingSession | None = None,
) -> None:
    sessions = sorted(
        (
            item
            for item in cast(list[TrainingSession], week.sessions)
            if item is not excluding
        ),
        key=lambda item: (item.position, item.id or 0),
    )
    for position, item in enumerate(sessions, start=1):
        item.position = position


def create(
    week: TrainingWeek,
    *,
    name: str,
    day_label: str | None,
) -> TrainingSession:
    position = len(week.sessions) + 1
    session = TrainingSession(
        week=week,
        name=name or f"Session {position}",
        day_label=day_label,
        position=position,
    )
    db.session.add(session)
    _commit_or_rollback()
    return session


def insert_blank(source: TrainingSession, *, after: bool) -> TrainingSession:
    week = cast(TrainingWeek, source.week)
    renumber(week)
    insertion_position = source.position + int(after)
    for item in cast(list[TrainingSession], week.sessions):
        if item.position >= insertion_position:
            item.position += 1
    target = TrainingSession(
        week=week,
        name=f"Session {insertion_position}",
        position=insertion_position,
    )
    db.session.add(target)
    _commit_or_rollback()
    return target


def duplicate(source: TrainingSession) -> TrainingSession:
    try:
        week = cast(TrainingWeek, source.week)
        renumber(week)
        target_position = source.position + 1
        for existing_session in cast(list[TrainingSession], week.sessions):
            if existing_session.position >= target_position:
                existing_session.position += 1
        target = TrainingSession(
            week=week,
            name=f"{source.name} Copy",
            day_label=source.day_label,
            position=target_position,
            notes=source.notes,
        )
        db.session.add(target)
        db.session.flush()
        copy_prescriptions(source, target)
        copy_warmups(source, target)
        _commit_or_rollback()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return target


def delete(session: TrainingSession) -> int:
    week = cast(TrainingWeek, session.week)
    week_id = week.id
    try:
        db.session.delete(session)
        renumber(week, excluding=session)
        _commit_or_rollback()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return week_id
