from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from ..extensions import db


class AccountTokenPurpose(StrEnum):
    INVITATION = "invitation"
    PASSWORD_RESET = "password_reset"


class DeliveryState(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    NOT_CONFIGURED = "not_configured"
    FAILED = "failed"


class AccountToken(db.Model):  # type: ignore[name-defined]
    __tablename__ = "account_tokens"
    __table_args__ = (
        db.CheckConstraint(
            "purpose IN ('invitation', 'password_reset')",
            name="ck_account_tokens_purpose",
        ),
        db.CheckConstraint(
            "delivery_state IN ('pending', 'sent', 'not_configured', 'failed')",
            name="ck_account_tokens_delivery_state",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    purpose = db.Column(db.String(32), nullable=False, index=True)
    token_digest = db.Column(db.String(64), nullable=False, unique=True, index=True)
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    consumed_at = db.Column(db.DateTime, nullable=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    delivery_state = db.Column(
        db.String(24), nullable=False, default=DeliveryState.PENDING
    )
    delivery_detail = db.Column(db.String(500), nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)

    athlete = db.relationship("Athlete")
    user = db.relationship("User", backref=db.backref("account_tokens", lazy="dynamic"))

    @property
    def is_available(self) -> bool:
        now = datetime.now(UTC)
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return (
            self.consumed_at is None
            and self.revoked_at is None
            and expires_at > now
        )
