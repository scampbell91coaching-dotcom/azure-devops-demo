from typing import cast

from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models.programming import TrainingSession, TrainingWeek
from .prescriptions import copy as copy_prescriptions
from .warmups import copy as copy_warmups
from .revisions import append_revision


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
    append_revision(week.block, change_type="session_created", summary=f'Added session "{session.name}"')
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
    append_revision(week.block, change_type="session_inserted", summary=f'Inserted session "{target.name}"')
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
        lift_slots = copy_prescriptions(source, target)
        copy_warmups(source, target, lift_slots)
        append_revision(week.block, change_type="session_duplicated", summary=f'Duplicated session "{source.name}"')
        _commit_or_rollback()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return target


def copy_to_week(source: TrainingSession, target_week: TrainingWeek) -> TrainingSession:
    """Copy authored session structure to an explicitly selected later week."""
    if source.week.block_id != target_week.block_id:
        raise ValueError("The destination must be in the same programme.")
    if target_week.position <= source.week.position:
        raise ValueError("Copy-forward destinations must be later programme weeks.")
    try:
        renumber(target_week)
        target = TrainingSession(week=target_week, name=source.name,
            day_label=source.day_label, position=len(target_week.sessions) + 1, notes=source.notes)
        db.session.add(target)
        db.session.flush()
        lift_slots = copy_prescriptions(source, target)
        copy_warmups(source, target, lift_slots)
        append_revision(target_week.block, change_type="session_copied_forward",
            summary=f'Copied session "{source.name}" to week {target_week.position}')
        _commit_or_rollback()
        return target
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        raise


def move(source: TrainingSession, target_week: TrainingWeek) -> TrainingSession:
    """Move structure only; the stable session id keeps all logs/results attached."""
    source_week = cast(TrainingWeek, source.week)
    if source_week.block_id != target_week.block_id:
        raise ValueError("The destination must be a week in the same programme.")
    if source_week.id == target_week.id:
        raise ValueError("Choose a different destination week.")
    try:
        source.week = target_week
        renumber(source_week, excluding=source)
        renumber(target_week, excluding=source)
        source.position = len([item for item in target_week.sessions if item is not source]) + 1
        append_revision(target_week.block, change_type="session_moved", summary=f'Moved session "{source.name}" from week {source_week.position} to week {target_week.position}')
        _commit_or_rollback()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        raise
    return source


def delete(session: TrainingSession) -> int:
    week = cast(TrainingWeek, session.week)
    week_id = week.id
    try:
        db.session.delete(session)
        renumber(week, excluding=session)
        append_revision(week.block, change_type="session_deleted", summary=f'Deleted session "{session.name}"')
        _commit_or_rollback()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return week_id
