from __future__ import annotations

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
