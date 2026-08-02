from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class NutritionCheckIn(db.Model):  # type: ignore[name-defined]
    __tablename__ = "nutrition_checkins"

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    submitted_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    bodyweight_kg = db.Column(db.Float, nullable=True)
    average_calories = db.Column(db.Integer, nullable=True)
    average_protein_g = db.Column(db.Integer, nullable=True)
    average_steps = db.Column(db.Integer, nullable=True)

    nutrition_adherence = db.Column(db.Integer, nullable=False)
    hunger = db.Column(db.Integer, nullable=False)
    energy = db.Column(db.Integer, nullable=False)
    sleep_quality = db.Column(db.Integer, nullable=False)
    stress = db.Column(db.Integer, nullable=False)
    digestion = db.Column(db.Integer, nullable=False)
    training_performance = db.Column(db.Integer, nullable=False)

    wins = db.Column(db.Text, nullable=True)
    challenges = db.Column(db.Text, nullable=True)
    upcoming_events = db.Column(db.Text, nullable=True)
    questions = db.Column(db.Text, nullable=True)

    coach_response = db.Column(db.Text, nullable=True)
    reviewed = db.Column(db.Boolean, nullable=False, default=False, index=True)

    athlete = db.relationship(
        "Athlete",
        back_populates="nutrition_checkins",
    )
