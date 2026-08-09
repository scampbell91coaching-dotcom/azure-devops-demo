from __future__ import annotations

from ..models.exercise_library import Exercise


class AccessoryRepository:
    """Database boundary for coach-enabled automatic accessory records."""

    def automatic_candidates(self) -> list[Exercise]:
        return (
            Exercise.query.filter(
                Exercise.active.is_(True),
                Exercise.accessory_suitable.is_(True),
                Exercise.auto_select.is_(True),
            )
            .order_by(
                Exercise.coach_priority.desc(),
                Exercise.fatigue_rating.asc(),
                Exercise.name.asc(),
            )
            .all()
        )
