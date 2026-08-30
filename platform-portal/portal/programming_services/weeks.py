from typing import cast

from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models.programming import (
    ExercisePrescription,
    TrainingBlock,
    TrainingSession,
    TrainingSessionLog,
    TrainingSetResult,
    TrainingWeek,
)
from .prescriptions import copy as copy_prescriptions
from .revisions import append_revision
from .warmups import copy as copy_warmups


class FinalWeekDeletionError(ValueError):
    """Raised when deleting a block's only remaining week is attempted."""


class InvalidWeekPositionError(ValueError):
    """Raised when a requested week position is outside its block."""


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
    append_revision(block, change_type="week_created", summary=f'Added week "{week.name}"')
    _commit_or_rollback()
    return week


def update(
    week: TrainingWeek, *, name: str, notes: str | None
) -> TrainingWeek:
    if not name:
        raise ValueError("week name is required")
    week.name = name
    week.notes = notes
    append_revision(
        week.block, change_type="week_updated", summary=f'Updated week "{name}"'
    )
    _commit_or_rollback()
    return week


def reorder(week: TrainingWeek, *, position: int) -> TrainingWeek:
    block = cast(TrainingBlock, week.block)
    renumber(block)
    if position < 1 or position > len(block.weeks):
        raise InvalidWeekPositionError("week position is outside the block")
    old_position = week.position
    if position == old_position:
        return week
    for item in cast(list[TrainingWeek], block.weeks):
        if item is week:
            continue
        if old_position < position and old_position < item.position <= position:
            item.position -= 1
        elif position < old_position and position <= item.position < old_position:
            item.position += 1
    week.position = position
    append_revision(
        block,
        change_type="weeks_reordered",
        summary=f'Moved week "{week.name}" to position {position}',
    )
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
        lift_slots = copy_prescriptions(source_session, target_session)
        copy_warmups(source_session, target_session, lift_slots)
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
        append_revision(block, change_type="week_duplicated", summary=f'Duplicated week "{source.name}"')
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
        append_revision(block, change_type="block_extended", summary=f"Extended programme by {count} week(s)")
        _commit_or_rollback()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return target


def detach_history(week: TrainingWeek) -> None:
    """Sever mutable programming links without deleting immutable history."""
    session_ids = [item.id for item in week.sessions if item.id is not None]
    if not session_ids:
        return
    prescription_ids = [
        row[0]
        for row in db.session.query(ExercisePrescription.id)
        .filter(ExercisePrescription.session_id.in_(session_ids))
        .all()
    ]
    if prescription_ids:
        TrainingSetResult.query.filter(
            TrainingSetResult.prescription_id.in_(prescription_ids)
        ).update({TrainingSetResult.prescription_id: None}, synchronize_session=False)
    TrainingSessionLog.query.filter(
        TrainingSessionLog.session_id.in_(session_ids)
    ).update({TrainingSessionLog.session_id: None}, synchronize_session=False)


def delete(week: TrainingWeek) -> int:
    block = cast(TrainingBlock, week.block)
    if len(block.weeks) <= 1:
        raise FinalWeekDeletionError("the final remaining week cannot be deleted")

    block_id = block.id
    try:
        detach_history(week)
        db.session.delete(week)
        renumber(block, excluding=week)
        append_revision(block, change_type="week_deleted", summary=f'Deleted week "{week.name}"')
        _commit_or_rollback()
    except SQLAlchemyError:
        db.session.rollback()
        raise
    return block_id
