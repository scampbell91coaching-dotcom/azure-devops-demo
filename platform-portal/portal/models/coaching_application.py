from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class CoachingApplication(db.Model):  # type: ignore[name-defined]
    __tablename__ = "coaching_applications"

    id = db.Column(db.Integer, primary_key=True)
    submitted_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    instagram = db.Column(db.String(120), nullable=True)
    country = db.Column(db.String(100), nullable=False)

    age = db.Column(db.Integer, nullable=True)
    bodyweight_kg = db.Column(db.Float, nullable=True)
    years_training = db.Column(db.Float, nullable=True)

    squat_kg = db.Column(db.Float, nullable=True)
    bench_kg = db.Column(db.Float, nullable=True)
    deadlift_kg = db.Column(db.Float, nullable=True)

    next_competition = db.Column(db.String(160), nullable=True)
    current_program = db.Column(db.Text, nullable=True)
    previous_coaching = db.Column(db.Text, nullable=True)

    primary_goal = db.Column(db.Text, nullable=False)
    biggest_problem = db.Column(db.Text, nullable=False)
    injury_history = db.Column(db.Text, nullable=True)
    coaching_expectations = db.Column(db.Text, nullable=False)

    training_days = db.Column(db.Integer, nullable=True)
    video_feedback_ready = db.Column(db.Boolean, nullable=False, default=False)
    communication_ready = db.Column(db.Boolean, nullable=False, default=False)
    minimum_term_ready = db.Column(db.Boolean, nullable=False, default=False)

    referral_source = db.Column(db.String(160), nullable=True)
    anything_else = db.Column(db.Text, nullable=True)

    privacy_consent = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(40), nullable=False, default="new", index=True)
