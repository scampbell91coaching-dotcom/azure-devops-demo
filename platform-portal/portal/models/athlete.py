from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class Athlete(db.Model):  # type: ignore[name-defined]
    __tablename__ = "athletes"

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    instagram = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(40), nullable=False, default="active", index=True)

    bodyweight_kg = db.Column(db.Float, nullable=True)
    weight_class = db.Column(db.String(40), nullable=True)
    federation = db.Column(db.String(80), nullable=True)
    next_competition = db.Column(db.String(160), nullable=True)

    coach_notes = db.Column(db.Text, nullable=True)

    nutrition_checkins = db.relationship(
        "NutritionCheckIn",
        back_populates="athlete",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
