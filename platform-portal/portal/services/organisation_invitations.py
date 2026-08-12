from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models.organisation import (
    InvitationDeliveryState, InvitationStatus, MembershipStatus, Organisation,
    OrganisationInvitation, OrganisationMembership, OrganisationRole,
)
from ..models.user import User


class OrganisationInvitationError(ValueError):
    """A deliberately non-specific invitation failure safe for user-facing use."""


class DeliveryResult(Protocol):
    state: str
    detail: str | None


@dataclass(frozen=True)
class IssuedOrganisationInvitation:
    invitation: OrganisationInvitation
    raw_token: str


InvitationDelivery = Callable[[IssuedOrganisationInvitation], DeliveryResult]


def digest_invitation_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _active_issuer(membership_id: int, organisation_id: int) -> OrganisationMembership:
    membership = db.session.get(OrganisationMembership, membership_id)
    if (membership is None or membership.organisation_id != organisation_id
            or membership.status != MembershipStatus.ACTIVE):
        raise OrganisationInvitationError("An active issuer membership is required.")
    return membership


def issue_invitation(
    organisation_id: int, email: str, role: OrganisationRole | str,
    invited_by_membership_id: int, *, lifetime: timedelta,
    delivery: InvitationDelivery | None = None, at: datetime | None = None,
) -> IssuedOrganisationInvitation:
    """Persist a hashed, single-current invitation before attempting delivery."""
    now = at or datetime.now(UTC)
    if lifetime <= timedelta(0):
        raise OrganisationInvitationError("Invitation lifetime must be positive.")
    organisation = db.session.get(Organisation, organisation_id)
    if organisation is None or not organisation.active:
        raise OrganisationInvitationError("An active Organisation is required.")
    _active_issuer(invited_by_membership_id, organisation_id)
    normalised_email = email.strip().casefold()
    if not normalised_email or "@" not in normalised_email:
        raise OrganisationInvitationError("A valid invitation email is required.")
    for previous in OrganisationInvitation.query.filter_by(
        organisation_id=organisation_id, email_normalised=normalised_email,
        status=InvitationStatus.PENDING,
    ).all():
        previous.status = (InvitationStatus.EXPIRED if now >= _utc(previous.expires_at)
                           else InvitationStatus.SUPERSEDED)
    raw_token = secrets.token_urlsafe(32)
    invitation = OrganisationInvitation(
        organisation_id=organisation_id, email_normalised=normalised_email,
        role=OrganisationRole(role), status=InvitationStatus.PENDING,
        token_digest=digest_invitation_token(raw_token),
        invited_by_membership_id=invited_by_membership_id,
        expires_at=now + lifetime, delivery_state=InvitationDeliveryState.PENDING,
    )
    db.session.add(invitation)
    try:
        db.session.commit()
    except (IntegrityError, ValueError) as exc:
        db.session.rollback()
        raise OrganisationInvitationError("An invitation could not be issued.") from exc
    issued = IssuedOrganisationInvitation(invitation, raw_token)
    if delivery is None:
        invitation.delivery_state = InvitationDeliveryState.NOT_CONFIGURED
        db.session.commit()
    else:
        try:
            result = delivery(issued)
            state, detail = InvitationDeliveryState(result.state), result.detail
        except Exception:  # noqa: BLE001
            state, detail = InvitationDeliveryState.FAILED, "Invitation delivery failed."
        invitation.delivery_state = state
        invitation.delivery_detail = detail[:500] if detail else None
        invitation.delivered_at = now if state == InvitationDeliveryState.SENT else None
        db.session.commit()
    return issued


def invitation_for_token(raw_token: str) -> OrganisationInvitation | None:
    if not raw_token or len(raw_token) > 200:
        return None
    return OrganisationInvitation.query.filter_by(
        token_digest=digest_invitation_token(raw_token)
    ).first()


def accept_invitation(raw_token: str, user: User, *, at: datetime | None = None) -> OrganisationMembership:
    """Atomically consume an invitation and create its canonical membership."""
    now = at or datetime.now(UTC)
    invitation = invitation_for_token(raw_token)
    invalid = "This invitation is invalid or unavailable."
    if (invitation is None or user.id is None
            or user.email.strip().casefold() != invitation.email_normalised
            or invitation.status != InvitationStatus.PENDING):
        raise OrganisationInvitationError(invalid)
    if now >= _utc(invitation.expires_at):
        db.session.execute(update(OrganisationInvitation).where(
            OrganisationInvitation.id == invitation.id,
            OrganisationInvitation.status == InvitationStatus.PENDING,
        ).values(status=InvitationStatus.EXPIRED, updated_at=now))
        db.session.commit()
        raise OrganisationInvitationError(invalid)
    _active_issuer(invitation.invited_by_membership_id, invitation.organisation_id)
    organisation = db.session.get(Organisation, invitation.organisation_id)
    if organisation is None or not organisation.active or OrganisationMembership.query.filter_by(
        organisation_id=invitation.organisation_id, user_id=user.id
    ).first() is not None:
        raise OrganisationInvitationError(invalid)
    claimed = db.session.execute(update(OrganisationInvitation).where(
        OrganisationInvitation.id == invitation.id,
        OrganisationInvitation.status == InvitationStatus.PENDING,
        OrganisationInvitation.expires_at > now,
    ).values(status=InvitationStatus.ACCEPTED, accepted_by_user_id=user.id,
             accepted_at=now, updated_at=now).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        db.session.rollback()
        raise OrganisationInvitationError(invalid)
    membership = OrganisationMembership(
        organisation_id=invitation.organisation_id, user_id=user.id,
        role=invitation.role, status=MembershipStatus.ACTIVE,
    )
    db.session.add(membership)
    try:
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise OrganisationInvitationError(invalid) from exc
    return membership


def revoke_invitation(invitation_id: int, issuer_membership_id: int) -> bool:
    invitation = db.session.get(OrganisationInvitation, invitation_id)
    if invitation is None:
        return False
    _active_issuer(issuer_membership_id, invitation.organisation_id)
    result = db.session.execute(update(OrganisationInvitation).where(
        OrganisationInvitation.id == invitation_id,
        OrganisationInvitation.status == InvitationStatus.PENDING,
    ).values(status=InvitationStatus.REVOKED, updated_at=datetime.now(UTC)))
    db.session.commit()
    return result.rowcount == 1
