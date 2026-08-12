from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from ..billing.entitlements import SubscriptionState
from ..extensions import db


def _uuid() -> str:
    return str(uuid4())


class SubscriptionAccount(db.Model):  # type: ignore[name-defined]
    __tablename__ = "subscription_accounts"
    __table_args__ = (
        db.CheckConstraint(
            "state IN ('trialing', 'active', 'past_due', 'cancelled', 'incomplete')",
            name="ck_subscription_accounts_state",
        ),
        db.CheckConstraint(
            "(provider IS NULL AND provider_customer_id IS NULL AND provider_subscription_id IS NULL) OR "
            "(provider IS NOT NULL AND provider_customer_id IS NOT NULL AND provider_subscription_id IS NOT NULL)",
            name="ck_subscription_accounts_provider_identity",
        ),
        db.UniqueConstraint("provider", "provider_customer_id", name="uq_subscription_provider_customer"),
        db.UniqueConstraint("provider", "provider_subscription_id", name="uq_subscription_provider_subscription"),
    )

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    organisation_id = db.Column(
        db.Integer,
        db.ForeignKey("organisations.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    plan_identifier = db.Column(db.String(100), nullable=False, index=True)
    state = db.Column(db.String(20), nullable=False)
    provider = db.Column(db.String(50), nullable=True)
    provider_customer_id = db.Column(db.String(255), nullable=True)
    provider_subscription_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    organisation = db.relationship("Organisation", backref=db.backref("subscription_account", uselist=False))

    @property
    def subscription_state(self) -> SubscriptionState:
        return SubscriptionState(self.state)


class BillingWebhookEvent(db.Model):  # type: ignore[name-defined]
    __tablename__ = "billing_webhook_events"
    __table_args__ = (
        db.UniqueConstraint("provider", "event_id", name="uq_billing_webhook_provider_event"),
        db.CheckConstraint(
            "status IN ('processing', 'processed', 'failed')",
            name="ck_billing_webhook_events_status",
        ),
    )

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    provider = db.Column(db.String(50), nullable=False)
    event_id = db.Column(db.String(255), nullable=False)
    payload_digest = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    received_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    processed_at = db.Column(db.DateTime, nullable=True)
