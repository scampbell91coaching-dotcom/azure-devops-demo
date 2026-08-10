"""Canonical policy for athlete nutrition coaching access.

The existing check-in settings row is the migration-free client entitlement
source.  A missing row predates entitlements and remains enabled for backwards
compatibility; all newly-created athletes receive an explicit disabled row.
"""

from __future__ import annotations

from ..models.athlete import Athlete
from ..models.checkins import AthleteCheckinSettings


def nutrition_coaching_enabled(athlete_or_id: Athlete | int) -> bool:
    """Return whether active nutrition coaching is available to an athlete."""
    athlete_id = (
        athlete_or_id.id if isinstance(athlete_or_id, Athlete) else athlete_or_id
    )
    settings = AthleteCheckinSettings.query.filter_by(athlete_id=athlete_id).first()
    return True if settings is None else bool(settings.nutrition_enabled)

