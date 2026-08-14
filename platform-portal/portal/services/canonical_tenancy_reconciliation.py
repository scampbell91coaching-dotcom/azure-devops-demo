"""Conservative reconciliation for legacy single-tenant installations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..extensions import db
from ..models.athlete import Athlete
from ..models.organisation import (
    CoachAthleteOwnership,
    MembershipStatus,
    Organisation,
    OrganisationMembership,
    OrganisationRole,
    OwnershipStatus,
)
from ..models.user import User, UserRole


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    mode: str
    status: str
    organisation_id: int | None = None
    coach_user_id: int | None = None
    membership_id: int | None = None
    missing_membership: bool = False
    missing_ownership_athlete_ids: list[int] = field(default_factory=list)
    changes_applied: int = 0
    blockers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def reconcile_canonical_tenancy(*, apply: bool = False) -> ReconciliationReport:
    """Plan or apply the only unambiguous legacy bootstrap.

    The safe case is exactly one active Organisation and exactly one active
    global coach. Existing inactive lifecycle rows are blockers, not candidates
    for reactivation. The caller owns transaction commit/rollback.
    """
    mode = "apply" if apply else "dry-run"
    organisations = Organisation.query.order_by(Organisation.id).all()
    active_organisations = [item for item in organisations if item.active]
    if not organisations:
        return ReconciliationReport(
            mode=mode,
            status="refused",
            blockers=[
                "No organisation exists. Create the intended organisation through the "
                "approved onboarding flow, then run reconciliation again."
            ],
        )
    if len(organisations) != 1 or len(active_organisations) != 1:
        return ReconciliationReport(
            mode=mode,
            status="refused",
            blockers=[
                "Expected exactly one active organisation for safe bootstrap; found "
                f"{len(organisations)} total and {len(active_organisations)} active. "
                "Resolve organisation scope explicitly; no organisation was selected."
            ],
        )

    organisation = active_organisations[0]
    coaches = (
        User.query.filter(User.role == UserRole.COACH, User.active.is_(True))
        .order_by(User.id)
        .all()
    )
    if len(coaches) != 1:
        return ReconciliationReport(
            mode=mode,
            status="refused",
            organisation_id=organisation.id,
            blockers=[
                "Expected exactly one active coach identity for safe bootstrap; found "
                f"{len(coaches)}. Assign memberships and athlete ownerships explicitly."
            ],
        )
    coach = coaches[0]
    membership = OrganisationMembership.query.filter_by(
        organisation_id=organisation.id, user_id=coach.id
    ).one_or_none()
    if membership is not None and membership.status != MembershipStatus.ACTIVE:
        return ReconciliationReport(
            mode=mode,
            status="refused",
            organisation_id=organisation.id,
            coach_user_id=coach.id,
            membership_id=membership.id,
            blockers=[
                f"Membership {membership.id} is inactive. Reactivation is a deliberate "
                "lifecycle action and was not performed."
            ],
        )

    inactive_ownerships = (
        CoachAthleteOwnership.query.filter_by(
            organisation_id=organisation.id, status=OwnershipStatus.INACTIVE
        )
        .order_by(CoachAthleteOwnership.athlete_id)
        .all()
    )
    if inactive_ownerships:
        ids = [row.athlete_id for row in inactive_ownerships]
        return ReconciliationReport(
            mode=mode,
            status="refused",
            organisation_id=organisation.id,
            coach_user_id=coach.id,
            membership_id=membership.id if membership else None,
            blockers=[
                "Inactive ownerships exist for athlete IDs "
                f"{ids}. Reactivation is a deliberate lifecycle action and was not performed."
            ],
        )

    athletes = Athlete.query.order_by(Athlete.id).all()
    active_ownerships = CoachAthleteOwnership.query.filter_by(
        organisation_id=organisation.id, status=OwnershipStatus.ACTIVE
    ).all()
    wrong_coach = [
        row.athlete_id
        for row in active_ownerships
        if membership is None or row.coach_membership_id != membership.id
    ]
    if wrong_coach:
        return ReconciliationReport(
            mode=mode,
            status="refused",
            organisation_id=organisation.id,
            coach_user_id=coach.id,
            membership_id=membership.id if membership else None,
            blockers=[
                "Active ownerships do not belong to the sole coach membership for athlete "
                f"IDs {sorted(wrong_coach)}. Review these assignments explicitly."
            ],
        )

    owned_ids = {row.athlete_id for row in active_ownerships}
    missing_ids = [athlete.id for athlete in athletes if athlete.id not in owned_ids]
    missing_membership = membership is None
    planned_changes = int(missing_membership) + len(missing_ids)
    if not apply:
        return ReconciliationReport(
            mode=mode,
            status="changes-required" if planned_changes else "healthy",
            organisation_id=organisation.id,
            coach_user_id=coach.id,
            membership_id=membership.id if membership else None,
            missing_membership=missing_membership,
            missing_ownership_athlete_ids=missing_ids,
        )

    if membership is None:
        membership = OrganisationMembership(
            organisation_id=organisation.id,
            user_id=coach.id,
            role=OrganisationRole.OWNER,
            status=MembershipStatus.ACTIVE,
        )
        db.session.add(membership)
        db.session.flush()
    for athlete_id in missing_ids:
        db.session.add(
            CoachAthleteOwnership(
                organisation_id=organisation.id,
                coach_membership_id=membership.id,
                athlete_id=athlete_id,
                status=OwnershipStatus.ACTIVE,
            )
        )
    db.session.commit()
    return ReconciliationReport(
        mode=mode,
        status="applied" if planned_changes else "healthy",
        organisation_id=organisation.id,
        coach_user_id=coach.id,
        membership_id=membership.id,
        changes_applied=planned_changes,
    )
