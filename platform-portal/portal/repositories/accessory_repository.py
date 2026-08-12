from __future__ import annotations

from sqlalchemy import or_

from ..models.exercise_library import Exercise


class AccessoryRepository:
    """Database boundary for active, accessory-suitable catalogue records."""

    def automatic_candidates(self) -> list[Exercise]:
        return (
            Exercise.query.filter(
                Exercise.active.is_(True),
                Exercise.accessory_suitable.is_(True),
            )
            .order_by(
                Exercise.auto_select.desc(),
                Exercise.coach_priority.desc(),
                Exercise.fatigue_rating.asc(),
                Exercise.name.asc(),
            )
            .all()
        )

    def selection_candidates(self, *, include_ids: set[int] | None = None) -> list[Exercise]:
        """Return the explainable-ranking pool, including ineligible rows.

        Ranking, rather than the database boundary, records why a catalogue row
        was excluded. The stable ID tie-break makes the result reproducible when
        names are duplicated in imported/legacy data.
        """
        include_ids = include_ids or set()
        eligibility = or_(Exercise.accessory_suitable.is_(True), Exercise.auto_select.is_(True))
        if include_ids:
            eligibility = or_(eligibility, Exercise.id.in_(include_ids))
        return (
            Exercise.query.filter(eligibility)
            .order_by(Exercise.name.asc(), Exercise.id.asc())
            .all()
        )
