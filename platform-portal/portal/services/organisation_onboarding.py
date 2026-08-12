from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from ..billing.entitlements import DEFAULT_PLANS, EntitlementDecision, EntitlementService, LimitKind, SubscriptionSnapshot
from ..extensions import db
from ..models.athlete import Athlete
from ..models.billing import SubscriptionAccount
from ..models.organisation import CoachAthleteOwnership, MembershipStatus, Organisation, OrganisationInvitation, OrganisationMembership, OrganisationRole, OwnershipStatus
from ..models.user import User
from .organisation_invitations import IssuedOrganisationInvitation, issue_invitation


class OrganisationOnboardingError(ValueError): pass
class OrganisationAccessDenied(PermissionError): pass


class OrganisationEntitlementDenied(PermissionError):
    def __init__(self, decision: EntitlementDecision):
        self.decision = decision
        super().__init__(decision.reason)


@dataclass(frozen=True, slots=True)
class OrganisationOnboarding:
    organisation: Organisation
    owner_membership: OrganisationMembership
    coach_invitations: tuple[OrganisationInvitation, ...]
    athlete_ownerships: tuple[CoachAthleteOwnership, ...]
    subscription: SubscriptionAccount | None
    current_step: str

    @property
    def ready(self) -> bool: return self.current_step == "ready"


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.strip().casefold()).strip("-")
    if not result: raise OrganisationOnboardingError("Enter an Organisation name.")
    return result[:80]


def create_organisation(*, name: str, owner: User) -> Organisation:
    clean = name.strip()
    if not clean or len(clean) > 160:
        raise OrganisationOnboardingError("Enter an Organisation name of 160 characters or fewer.")
    organisation = Organisation(name=clean, slug=_slug(clean))
    membership = OrganisationMembership(organisation=organisation, user=owner,
        role=OrganisationRole.OWNER, status=MembershipStatus.ACTIVE)
    db.session.add_all((organisation, membership))
    try: db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise OrganisationOnboardingError("That Organisation name is already in use.") from exc
    return organisation


def require_membership(user_id: int, organisation_id: int, *, roles: frozenset[OrganisationRole] | None = None) -> OrganisationMembership:
    membership = OrganisationMembership.query.filter_by(user_id=user_id,
        organisation_id=organisation_id, status=MembershipStatus.ACTIVE).first()
    if membership is None or (roles is not None and membership.role not in roles):
        raise OrganisationAccessDenied("Organisation membership is required.")
    return membership


def build_onboarding(organisation: Organisation, owner: OrganisationMembership) -> OrganisationOnboarding:
    if (owner.organisation_id != organisation.id or owner.role != OrganisationRole.OWNER
            or owner.status != MembershipStatus.ACTIVE):
        raise OrganisationAccessDenied("Organisation owner membership is required.")
    invitations = tuple(OrganisationInvitation.query.filter_by(
        organisation_id=organisation.id, role=OrganisationRole.COACH).all())
    ownerships = tuple(CoachAthleteOwnership.query.filter_by(
        organisation_id=organisation.id, status=OwnershipStatus.ACTIVE).all())
    subscription = SubscriptionAccount.query.filter_by(organisation_id=organisation.id).first()
    current = "athletes" if not ownerships else "plan" if subscription is None else "ready"
    return OrganisationOnboarding(organisation, owner, invitations, ownerships, subscription, current)


def invite_coach(*, organisation: Organisation, inviter: OrganisationMembership,
                 email: str, lifetime: timedelta = timedelta(days=7)) -> IssuedOrganisationInvitation:
    if (inviter.organisation_id != organisation.id or inviter.status != MembershipStatus.ACTIVE
            or inviter.role not in {OrganisationRole.OWNER, OrganisationRole.ADMIN}):
        raise OrganisationAccessDenied("Organisation owner or admin membership is required.")
    return issue_invitation(organisation.id, email, OrganisationRole.COACH, inviter.id,
                            lifetime=lifetime)


def subscription_snapshot(organisation_id: int) -> SubscriptionSnapshot | None:
    account = SubscriptionAccount.query.filter_by(organisation_id=organisation_id).first()
    if account is None: return None
    try: return SubscriptionSnapshot(str(organisation_id), account.plan_identifier, account.subscription_state)
    except ValueError: return None


def require_capability(organisation_id: int, capability: str) -> EntitlementDecision:
    snapshot = subscription_snapshot(organisation_id)
    if snapshot is None:
        raise OrganisationEntitlementDenied(EntitlementDecision(False, "subscription_not_entitled"))
    decision = EntitlementService().capability(snapshot, capability)
    if not decision.allowed: raise OrganisationEntitlementDenied(decision)
    return decision


def assign_athlete(*, organisation: Organisation, coach_membership: OrganisationMembership, athlete: Athlete) -> CoachAthleteOwnership:
    if (not organisation.active or coach_membership.organisation_id != organisation.id
            or coach_membership.status != MembershipStatus.ACTIVE
            or coach_membership.role not in {OrganisationRole.OWNER, OrganisationRole.ADMIN, OrganisationRole.COACH}):
        raise OrganisationAccessDenied("An active coach membership in this Organisation is required.")
    existing = CoachAthleteOwnership.query.filter_by(athlete_id=athlete.id).first()
    if existing is not None and existing.organisation_id != organisation.id:
        raise OrganisationAccessDenied("Athlete is not available in this Organisation.")
    snapshot = subscription_snapshot(organisation.id)
    if SubscriptionAccount.query.filter_by(organisation_id=organisation.id).first() is not None and snapshot is None:
        raise OrganisationEntitlementDenied(EntitlementDecision(False, "subscription_not_entitled"))
    if snapshot is not None and existing is None:
        count = CoachAthleteOwnership.query.filter_by(organisation_id=organisation.id, status=OwnershipStatus.ACTIVE).count()
        decision = EntitlementService().capacity(snapshot, LimitKind.ATHLETES, count)
        if not decision.allowed: raise OrganisationEntitlementDenied(decision)
    ownership = existing or CoachAthleteOwnership(organisation_id=organisation.id, athlete=athlete)
    ownership.coach_membership_id, ownership.status = coach_membership.id, OwnershipStatus.ACTIVE
    db.session.add(ownership); db.session.commit(); return ownership


def select_plan(*, organisation: Organisation, identifier: str) -> SubscriptionAccount:
    if identifier not in DEFAULT_PLANS:
        raise OrganisationOnboardingError("Choose a recognised powerlifting coaching plan.")
    count = CoachAthleteOwnership.query.filter_by(organisation_id=organisation.id, status=OwnershipStatus.ACTIVE).count()
    plan = DEFAULT_PLANS[identifier]
    if plan.athlete_limit is not None and count > plan.athlete_limit:
        raise OrganisationOnboardingError(f"{identifier.title()} supports {plan.athlete_limit} athletes; this Organisation already has {count}.")
    account = SubscriptionAccount.query.filter_by(organisation_id=organisation.id).first()
    if account is None:
        account = SubscriptionAccount(organisation_id=organisation.id, plan_identifier=identifier, state="trialing")
        db.session.add(account)
    else: account.plan_identifier = identifier
    db.session.commit(); return account
