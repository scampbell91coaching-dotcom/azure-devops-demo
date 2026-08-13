from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class SupportPrincipalRecord(db.Model):  # type: ignore[name-defined]
    """Explicit support identity; creating an application user grants nothing."""

    __tablename__ = "support_principals"

    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(255), nullable=False, unique=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))


class SupportCapabilityGrant(db.Model):  # type: ignore[name-defined]
    __tablename__ = "support_capability_grants"
    __table_args__ = (
        db.UniqueConstraint("principal_id", "capability", name="uq_support_capability_grant"),
    )

    id = db.Column(db.Integer, primary_key=True)
    principal_id = db.Column(
        db.Integer, db.ForeignKey("support_principals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability = db.Column(db.String(64), nullable=False)
    granted_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    revoked_at = db.Column(db.DateTime, nullable=True)


class SupportAccessEvent(db.Model):  # type: ignore[name-defined]
    """Append-only security record; application code must never update/delete rows."""

    __tablename__ = "support_access_events"
    __table_args__ = (
        db.CheckConstraint("visibility IN ('tenant', 'internal')", name="ck_support_event_visibility"),
    )

    id = db.Column(db.Integer, primary_key=True)
    principal_id = db.Column(
        db.Integer, db.ForeignKey("support_principals.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tenant_ref = db.Column(db.String(255), nullable=False, index=True)
    action = db.Column(db.String(64), nullable=False, index=True)
    capability = db.Column(db.String(64), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    reference = db.Column(db.String(255), nullable=False, index=True)
    target_account_ref = db.Column(db.String(255), nullable=True)
    visibility = db.Column(db.String(16), nullable=False, default="tenant")
    occurred_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC), index=True)
    details = db.Column(db.JSON, nullable=False, default=dict)


class SupportDelegation(db.Model):  # type: ignore[name-defined]
    __tablename__ = "support_delegations"
    __table_args__ = (
        db.CheckConstraint("expires_at > started_at", name="ck_support_delegation_period"),
    )

    id = db.Column(db.String(36), primary_key=True)
    principal_id = db.Column(
        db.Integer, db.ForeignKey("support_principals.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tenant_ref = db.Column(db.String(255), nullable=False, index=True)
    target_account_ref = db.Column(db.String(255), nullable=False)
    start_event_id = db.Column(
        db.Integer, db.ForeignKey("support_access_events.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    started_at = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    ended_at = db.Column(db.DateTime, nullable=True)
