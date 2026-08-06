from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from ..extensions import db

LIFTS = ("squat", "bench", "deadlift")
OUTCOMES = ("pending", "good", "miss", "skipped")


class Meet(db.Model):  # type: ignore[name-defined]
    __tablename__ = "meets"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('planned', 'active', 'complete')", name="ck_meets_status"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    meet_date = db.Column(
        db.Date, nullable=False, default=lambda: datetime.now(UTC).date(), index=True
    )
    status = db.Column(db.String(20), nullable=False, default="planned", index=True)
    federation = db.Column(db.String(80))
    bodyweight_kg = db.Column(db.Numeric(6, 2))
    weight_class = db.Column(db.String(40))
    notes = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    entries = db.relationship(
        "MeetEntry",
        back_populates="meet",
        cascade="all, delete-orphan",
        order_by="MeetEntry.flight, MeetEntry.platform_order",
    )


class MeetEntry(db.Model):  # type: ignore[name-defined]
    __tablename__ = "meet_entries"
    __table_args__ = (
        db.UniqueConstraint("meet_id", "athlete_id", name="uq_meet_entries_athlete"),
        db.CheckConstraint("flight >= 1", name="ck_meet_entries_flight"),
        db.CheckConstraint("platform_order >= 1", name="ck_meet_entries_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    meet_id = db.Column(
        db.Integer,
        db.ForeignKey("meets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    flight = db.Column(db.Integer, nullable=False, default=1)
    platform_order = db.Column(db.Integer, nullable=False, default=1)
    notes = db.Column(db.Text)

    meet = db.relationship("Meet", back_populates="entries")
    athlete = db.relationship("Athlete")
    lifts = db.relationship(
        "MeetLift",
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="MeetLift.lift, MeetLift.kind, MeetLift.sequence",
    )


class MeetLift(db.Model):  # type: ignore[name-defined]
    __tablename__ = "meet_lifts"
    __table_args__ = (
        db.UniqueConstraint(
            "entry_id", "lift", "kind", "sequence", name="uq_meet_lifts_slot"
        ),
        db.CheckConstraint(
            "lift IN ('squat', 'bench', 'deadlift')", name="ck_meet_lifts_lift"
        ),
        db.CheckConstraint("kind IN ('warmup', 'attempt')", name="ck_meet_lifts_kind"),
        db.CheckConstraint(
            "outcome IN ('pending', 'good', 'miss', 'skipped')",
            name="ck_meet_lifts_outcome",
        ),
        db.CheckConstraint("sequence >= 1", name="ck_meet_lifts_sequence"),
        db.CheckConstraint(
            "weight_kg IS NULL OR weight_kg > 0", name="ck_meet_lifts_weight"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(
        db.Integer,
        db.ForeignKey("meet_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lift = db.Column(db.String(20), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)
    weight_kg = db.Column(db.Numeric(6, 2), nullable=True)
    outcome = db.Column(db.String(20), nullable=False, default="pending")
    notes = db.Column(db.Text)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    entry = db.relationship("MeetEntry", back_populates="lifts")

    @property
    def display_weight(self) -> str:
        if self.weight_kg is None:
            return "—"
        return f"{Decimal(self.weight_kg):g} kg"
