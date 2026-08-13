from __future__ import annotations

from collections.abc import Iterable

from portal.extensions import db
from portal.models.athlete import Athlete
from portal.models.organisation import (
    CoachAthleteOwnership,
    Organisation,
    OrganisationMembership,
    OrganisationRole,
)
from portal.models.user import User


def grant_coach_athlete_access(
    coach: User,
    athletes: Iterable[Athlete] = (),
    *,
    name: str,
    slug: str,
) -> OrganisationMembership:
    """Seed the canonical authority graph used by authorised coach-route tests."""
    organisation = Organisation(name=name, slug=slug)
    membership = OrganisationMembership(
        organisation=organisation,
        user=coach,
        role=OrganisationRole.COACH,
    )
    db.session.add_all([organisation, membership])
    for athlete in athletes:
        db.session.add(
            CoachAthleteOwnership(
                organisation=organisation,
                coach_membership=membership,
                athlete=athlete,
            )
        )
    return membership
