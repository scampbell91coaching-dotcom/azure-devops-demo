from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db


class LeadCapture(db.Model):  # type: ignore[name-defined]
    __tablename__ = "lead_captures"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(320), nullable=False, index=True)
    source_slug = db.Column(db.String(120), nullable=False, index=True)
    consent = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
