from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy.orm import validates

from ..extensions import db


def _now() -> datetime:
    return datetime.now(UTC)


class OrganisationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    COACH = "coach"
    SUPPORT = "support"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class InvitationDeliveryState(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    NOT_CONFIGURED = "not_configured"
    FAILED = "failed"


class OwnershipStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Organisation(db.Model):  # type: ignore[name-defined]
    __tablename__ = "organisations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(80), nullable=False, unique=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)

    memberships = db.relationship(
        "OrganisationMembership", back_populates="organisation", lazy="dynamic"
    )

    @validates("slug")
    def normalise_slug(self, _key: str, value: str) -> str:
        normalised = value.strip().lower()
        if not normalised:
            raise ValueError("Organisation slug cannot be empty.")
        return normalised


class OrganisationMembership(db.Model):  # type: ignore[name-defined]
    __tablename__ = "organisation_memberships"
    __table_args__ = (
        db.CheckConstraint(
            "role IN ('owner', 'admin', 'coach', 'support')",
            name="ck_organisation_memberships_role",
        ),
        db.CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_organisation_memberships_status",
        ),
        db.UniqueConstraint(
            "organisation_id", "user_id", name="uq_organisation_membership_user"
        ),
        # Composite references use this key to make organisation scope structural.
        db.UniqueConstraint(
            "organisation_id", "id", name="uq_organisation_membership_scope"
        ),
        db.Index(
            "ix_organisation_memberships_org_status_role",
            "organisation_id", "status", "role",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    authorization_generation = db.Column(db.Integer, nullable=True)
    organisation_id = db.Column(
        db.Integer, db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    role = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=MembershipStatus.ACTIVE)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)

    organisation = db.relationship("Organisation", back_populates="memberships")
    user = db.relationship("User", backref=db.backref("organisation_memberships", lazy="dynamic"))


class CoachAthleteOwnership(db.Model):  # type: ignore[name-defined]
    __tablename__ = "coach_athlete_ownerships"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active', 'inactive')",
            name="ck_coach_athlete_ownerships_status",
        ),
        db.UniqueConstraint(
            "organisation_id", "athlete_id", name="uq_coach_athlete_ownership_org_athlete"
        ),
        db.ForeignKeyConstraint(
            ["organisation_id", "coach_membership_id"],
            ["organisation_memberships.organisation_id", "organisation_memberships.id"],
            name="fk_ownership_coach_membership_scope",
            ondelete="RESTRICT",
        ),
        db.Index(
            "ix_coach_athlete_ownerships_org_coach_status",
            "organisation_id", "coach_membership_id", "status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(
        db.Integer, db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    coach_membership_id = db.Column(db.Integer, nullable=False)
    athlete_id = db.Column(
        db.Integer, db.ForeignKey("athletes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status = db.Column(db.String(20), nullable=False, default=OwnershipStatus.ACTIVE)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)

    organisation = db.relationship("Organisation")
    coach_membership = db.relationship("OrganisationMembership", overlaps="organisation")
    athlete = db.relationship("Athlete", backref=db.backref("coach_ownerships", lazy="dynamic"))


class OrganisationInvitation(db.Model):  # type: ignore[name-defined]
    __tablename__ = "organisation_invitations"
    __table_args__ = (
        db.CheckConstraint(
            "role IN ('owner', 'admin', 'coach', 'support')",
            name="ck_organisation_invitations_role",
        ),
        db.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired', 'superseded')",
            name="ck_organisation_invitations_status",
        ),
        db.CheckConstraint(
            "delivery_state IN ('pending', 'sent', 'not_configured', 'failed')",
            name="ck_organisation_invitations_delivery_state",
        ),
        db.CheckConstraint(
            "(status = 'accepted' AND accepted_at IS NOT NULL AND accepted_by_user_id IS NOT NULL) "
            "OR (status <> 'accepted' AND accepted_at IS NULL AND accepted_by_user_id IS NULL)",
            name="ck_organisation_invitations_acceptance",
        ),
        db.ForeignKeyConstraint(
            ["organisation_id", "invited_by_membership_id"],
            ["organisation_memberships.organisation_id", "organisation_memberships.id"],
            name="fk_invitation_inviter_membership_scope",
            ondelete="RESTRICT",
        ),
        db.Index(
            "ix_organisation_invitations_org_status_email",
            "organisation_id", "status", "email_normalised",
        ),
        db.Index(
            "uq_organisation_invitations_pending_email",
            "organisation_id", "email_normalised",
            unique=True,
            sqlite_where=db.text("status = 'pending'"),
            postgresql_where=db.text("status = 'pending'"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(
        db.Integer, db.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False
    )
    email_normalised = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=InvitationStatus.PENDING)
    token_digest = db.Column(db.String(64), nullable=False, unique=True)
    delivery_state = db.Column(
        db.String(20), nullable=False, default=InvitationDeliveryState.PENDING
    )
    delivery_detail = db.Column(db.String(500), nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    invited_by_membership_id = db.Column(db.Integer, nullable=False)
    accepted_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)

    organisation = db.relationship("Organisation")
    invited_by_membership = db.relationship("OrganisationMembership", overlaps="organisation")
    accepted_by_user = db.relationship("User")

    @validates("email_normalised")
    def normalise_email(self, _key: str, value: str) -> str:
        normalised = value.strip().casefold()
        if not normalised or "@" not in normalised:
            raise ValueError("A valid invitation email is required.")
        return normalised

    def accept(self, user: "User", *, at: datetime | None = None) -> None:
        # SQLAlchemy column defaults are applied at INSERT time; a newly built
        # invitation is pending even before it has entered a session.
        if self.status not in (None, InvitationStatus.PENDING):
            raise ValueError("Only pending invitations can be accepted.")
        accepted_at = at or _now()
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if accepted_at >= expires_at:
            raise ValueError("Expired invitations cannot be accepted.")
        if user.email.strip().casefold() != self.email_normalised:
            raise ValueError("Invitation email does not match the accepting user.")
        self.status = InvitationStatus.ACCEPTED
        self.accepted_by_user = user
        self.accepted_at = accepted_at

    def revoke(self) -> None:
        if self.status not in (None, InvitationStatus.PENDING):
            raise ValueError("Only pending invitations can be revoked.")
        self.status = InvitationStatus.REVOKED

    def expire(self, *, at: datetime | None = None) -> None:
        if self.status not in (None, InvitationStatus.PENDING):
            raise ValueError("Only pending invitations can expire.")
        if (at or _now()) < self.expires_at.replace(tzinfo=self.expires_at.tzinfo or UTC):
            raise ValueError("Invitation has not expired yet.")
        self.status = InvitationStatus.EXPIRED

    def supersede(self) -> None:
        if self.status not in (None, InvitationStatus.PENDING):
            raise ValueError("Only pending invitations can be superseded.")
        self.status = InvitationStatus.SUPERSEDED
