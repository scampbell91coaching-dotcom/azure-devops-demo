from __future__ import annotations

from ..extensions import db
from ..models.programming import ProgrammeRevision, TrainingBlock


class ProgrammeConflictError(ValueError):
    """A recoverable optimistic-concurrency conflict."""


class ActiveProgrammeEditError(ValueError):
    """An athlete-visible graph must be revised through a draft."""


def require_editable(block: TrainingBlock) -> None:
    if block.status == "active":
        raise ActiveProgrammeEditError(
            "Create a review draft before changing an athlete-visible programme."
        )


def current_revision(block: TrainingBlock) -> int:
    return int(
        db.session.query(db.func.max(ProgrammeRevision.revision_number))
        .filter_by(block_id=block.id)
        .scalar()
        or 0
    )


def require_current(block: TrainingBlock, expected_revision: int | None) -> None:
    if expected_revision is None:
        return
    if current_revision(block) != expected_revision:
        raise ProgrammeConflictError(
            "This programme changed since you opened it. Reload to review the "
            "current saved version, then retry your change."
        )
