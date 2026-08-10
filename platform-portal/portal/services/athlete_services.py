from __future__ import annotations

from dataclasses import dataclass

from ..models.checkins import AthleteCheckinSettings
from .client_services import effective_client_service_profile


@dataclass(frozen=True)
class AthleteServices:
    """Effective athlete-facing coaching services."""

    training: bool
    nutrition: bool
    checkins: bool

    @property
    def combined(self) -> bool:
        return self.training and self.nutrition


def athlete_services(athlete_id: int) -> AthleteServices:
    profile = effective_client_service_profile(athlete_id)

    training = profile.training_coaching_enabled
    nutrition = profile.nutrition_coaching_enabled

    settings = AthleteCheckinSettings.query.filter_by(
        athlete_id=athlete_id
    ).first()

    if settings is None:
        # Legacy/no-settings behaviour: if the athlete has an active coaching
        # service, allow the standard check-in workflow.
        checkins = bool(training or nutrition)
    else:
        enabled_checkin_modules = bool(
            (training and settings.training_enabled)
            or (nutrition and settings.nutrition_enabled)
        )
        checkins = bool(
            settings.workflow_active
            and enabled_checkin_modules
        )

    return AthleteServices(
        training=training,
        nutrition=nutrition,
        checkins=checkins,
    )
