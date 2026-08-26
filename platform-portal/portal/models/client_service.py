from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class ClientServiceChange(db.Model):  # type: ignore[name-defined]
    """Append-only coach decisions used to resolve an athlete's services."""

    __tablename__ = "client_service_changes"
    __table_args__ = (
        db.CheckConstraint(
            "service IN ('training', 'nutrition', 'meet_day', 'video_review')",
            name="ck_client_service_changes_service",
        ),
        db.CheckConstraint(
            "value IN ('yes', 'no', 'none', 'limited', 'included')",
            name="ck_client_service_changes_value",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service = db.Column(db.String(32), nullable=False, index=True)
    value = db.Column(db.String(16), nullable=False)
    effective_at = db.Column(db.DateTime, nullable=False, index=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    changed_by_user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    athlete = db.relationship("Athlete", backref="client_service_changes")
    changed_by = db.relationship("User")
