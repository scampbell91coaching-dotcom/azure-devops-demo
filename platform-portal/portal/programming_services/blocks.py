from typing import cast

from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..models.athlete import Athlete
from ..models.programming import (
    ProgrammeRevision,
    TrainingBlock,
    TrainingSession,
    TrainingWeek,
)
from .prescriptions import copy as copy_prescriptions
from .conflicts import require_current
from .publication import publication_blockers
from .revisions import append_revision
from .warmups import copy as copy_warmups
from .weeks import detach_history


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


def update(
    block: TrainingBlock, *, name: str, objective: str | None
) -> TrainingBlock:
    if not name:
        raise ValueError("block name is required")
    block.name = name
    block.objective = objective
    append_revision(block, change_type="block_updated", summary="Updated block metadata")
    try:
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        raise
    return block


def duplicate(
    source: TrainingBlock, *, as_revision: bool = False
) -> TrainingBlock:
    try:
        target = TrainingBlock(
            athlete=source.athlete,
            name=f"{source.name} Copy",
            objective=source.objective,
            status="draft",
            replaces_block=source if as_revision else None,
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
                lift_slots = copy_prescriptions(source_session, target_session)
                copy_warmups(source_session, target_session, lift_slots)

        append_revision(
            target,
            change_type="material_change_draft_created" if as_revision else "block_duplicated",
            summary=(
                f'Created review draft from active programme "{source.name}"'
                if as_revision else f'Duplicated from "{source.name}"'
            ),
        )
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        raise
    return target


def activate(
    block: TrainingBlock,
    *,
    expected_revision: int | None = None,
    reason: str | None = None,
) -> None:
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

    require_current(block, expected_revision)
    blockers = publication_blockers(block)
    if blockers:
        raise BlockActivationError("Publication blocked: " + " ".join(blockers))

    replaced = block.replaces_block
    if replaced is not None:
        if replaced.athlete_id != block.athlete_id:
            raise BlockActivationError("The review draft does not match this athlete.")
        if replaced.status != "active":
            raise BlockActivationError(
                "The athlete-visible programme changed while this draft was reviewed. "
                "Reload and create a new review draft."
            )
        if not reason or not reason.strip():
            raise BlockActivationError("A reason is required for a material programme change.")

    conflicting = TrainingBlock.query.filter(
        TrainingBlock.athlete_id == block.athlete_id,
        TrainingBlock.status == "active",
        TrainingBlock.id != block.id,
    ).first()
    if conflicting is not None and conflicting is not replaced:
        raise BlockActivationError(
            f'Archive the active programme "{conflicting.name}" before publishing '
            "this draft."
        )

    try:
        if replaced is not None:
            replaced.status = "archived"
            append_revision(
                replaced,
                change_type="block_replaced",
                summary=f'Replaced by reviewed programme "{block.name}"',
                reason=reason,
            )
        block.status = "active"
        summary = (
            f'Published reviewed material changes replacing "{replaced.name}"'
            if replaced is not None else "Published programme to athlete"
        )
        append_revision(
            block,
            change_type="material_change_published" if replaced is not None else "block_published",
            summary=summary,
            reason=reason,
        )
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        raise


def archive(block: TrainingBlock) -> None:
    block.status = "archived"
    append_revision(block, change_type="block_archived", summary="Archived programme")
    db.session.commit()


def delete_draft(block: TrainingBlock) -> int:
    athlete_id = block.athlete_id
    try:
        # Logs/results contain authored snapshots and use SET NULL for their
        # programming links. Deleting draft structure must never delete history.
        for week in list(block.weeks):
            detach_history(week)
        # Preserve append-only provenance even when SQLite foreign-key actions
        # are unavailable in tests or local recovery tooling.
        ProgrammeRevision.query.filter_by(block_id=block.id).update(
            {ProgrammeRevision.block_id: None}, synchronize_session=False
        )
        db.session.delete(block)
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        raise
    return athlete_id
