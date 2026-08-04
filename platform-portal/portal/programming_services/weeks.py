from typing import cast

from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models.programming import TrainingBlock, TrainingSession, TrainingWeek
from .prescriptions import copy as copy_prescriptions


class FinalWeekDeletionError(ValueError):
    """Raised when deleting a block's only remaining week is attempted."""


def _commit_or_rollback() -> None:
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        raise


def renumber(
    block: TrainingBlock,
    *,
    excluding: TrainingWeek | None = None,
) -> None:
    weeks = sorted(
        (
            item
            for item in cast(list[TrainingWeek], block.weeks)
            if item is not excluding
        ),
        key=lambda item: (item.position, item.id or 0),
    )
    for position, item in enumerate(weeks, start=1):
        item.position = position


def create(
    block: TrainingBlock,
    *,
    name: str,
    notes: str | None,
) -> TrainingWeek:
    renumber(block)
    position = len(block.weeks) + 1
    week = TrainingWeek(
        block=block,
        name=name or f"Week {position}",
        position=position,
        notes=notes,
    )
    db.session.add(week)
    _commit_or_rollback()
    return week


def _copy(source: TrainingWeek, *, position: int) -> TrainingWeek:
    target = TrainingWeek(
        block=source.block,
        name=f"{source.name} Copy",
        position=position,
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
    return target


def duplicate(source: TrainingWeek) -> TrainingWeek:
    try:
        block = cast(TrainingBlock, source.block)
        renumber(block)
        target_position = source.position + 1
        for item in cast(list[TrainingWeek], block.weeks):
            if item.position >= target_position:
                item.position += 1
        target = _copy(source, position=target_position)
        _commit_or_rollback()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return target


def extend(block: TrainingBlock, *, count: int) -> TrainingWeek:
    if count < 1:
        raise ValueError("count must be at least one")
    if not block.weeks:
        raise ValueError("a block must contain a week before it can be extended")

    try:
        renumber(block)
        source = max(
            cast(list[TrainingWeek], block.weeks),
            key=lambda item: item.position,
        )
        target = source
        for _ in range(count):
            target = _copy(target, position=len(block.weeks) + 1)
        _commit_or_rollback()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return target


def delete(week: TrainingWeek) -> int:
    block = cast(TrainingBlock, week.block)
    if len(block.weeks) <= 1:
        raise FinalWeekDeletionError("the final remaining week cannot be deleted")

    block_id = block.id
    try:
        db.session.delete(week)
        renumber(block, excluding=week)
        _commit_or_rollback()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return block_id
