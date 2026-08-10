from __future__ import annotations

from .client_service_profiles import Service
from .client_services import may_start_client_service


def nutrition_coaching_enabled(athlete_or_id) -> bool:
    """Return whether the athlete currently receives nutrition coaching."""
    athlete_id = getattr(athlete_or_id, "id", athlete_or_id)

    return may_start_client_service(
        int(athlete_id),
        Service.NUTRITION_COACHING,
    )
