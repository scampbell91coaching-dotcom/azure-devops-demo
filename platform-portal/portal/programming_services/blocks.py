from typing import cast

from ..extensions import db
from ..models.athlete import Athlete
from ..models.programming import TrainingBlock, TrainingSession, TrainingWeek
from .prescriptions import copy as copy_prescriptions
from .warmups import copy as copy_warmups
from .revisions import append_revision


class BlockActivationError(ValueError):
    """Raised when a draft cannot safely become the athlete's active block."""


def create(
    athlete: Athlete,
    *,
    name: str,
    objective: str | None,
) -> TrainingBlock:
    block = TrainingBlock(athlete=athlete, name=name, objective=objective)
    db.session.add(block)
    db.session.flush()
    append_revision(block, change_type="block_created", summary="Created programme block")
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
            copy_warmups(source_session, target_session)

    append_revision(target, change_type="block_duplicated", summary=f'Duplicated from "{source.name}"')
    db.session.commit()
    return target


def activate(block: TrainingBlock) -> None:
    """Publish one draft without replacing an existing active programme."""
    # Serialize activation decisions for this athlete on databases that support
    # row locks, so two concurrent draft publishes cannot both pass the check.
    athlete = db.session.get(Athlete, block.athlete_id, with_for_update=True)
    if athlete is None or block.athlete is None:
        raise BlockActivationError(
            "This programme is not associated with a valid athlete."
        )
    if block.status == "active":
        return
    if block.status != "draft":
        raise BlockActivationError("Only draft programmes can be published.")

    conflicting = TrainingBlock.query.filter(
        TrainingBlock.athlete_id == block.athlete_id,
        TrainingBlock.status == "active",
        TrainingBlock.id != block.id,
    ).first()
    if conflicting is not None:
        raise BlockActivationError(
            f'Archive the active programme "{conflicting.name}" before publishing '
            "this draft."
        )

    block.status = "active"
    append_revision(block, change_type="block_published", summary="Published programme to athlete")
    db.session.commit()


def archive(block: TrainingBlock) -> None:
    block.status = "archived"
    append_revision(block, change_type="block_archived", summary="Archived programme")
    db.session.commit()


def delete_draft(block: TrainingBlock) -> int:
    athlete_id = block.athlete_id
    db.session.delete(block)
    db.session.commit()
    return athlete_id
