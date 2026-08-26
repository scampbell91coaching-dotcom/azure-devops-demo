from __future__ import annotations

from datetime import UTC, datetime

from ..extensions import db


class ExternalCoachingReview(db.Model):  # type: ignore[name-defined]
    """A coach-authored record of a review completed outside the platform.

    This stores the review outcome and optional links to existing coaching
    records. It deliberately stores no message body, media, or provider data.
    """

    __tablename__ = "external_coaching_reviews"
    __table_args__ = (
        db.CheckConstraint("channel = 'whatsapp'", name="ck_external_reviews_channel"),
    )

    id = db.Column(db.Integer, primary_key=True)
    organisation_id = db.Column(db.Integer, db.ForeignKey("organisations.id", ondelete="RESTRICT"), nullable=True, index=True)
    athlete_id = db.Column(
        db.Integer,
        db.ForeignKey("athletes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel = db.Column(db.String(20), nullable=False, default="whatsapp")
    reviewed_at = db.Column(db.DateTime, nullable=False, index=True)
    session_log_id = db.Column(
        db.Integer,
        db.ForeignKey("training_session_logs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    set_result_id = db.Column(
        db.Integer,
        db.ForeignKey("training_set_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    observation_id = db.Column(
        db.Integer,
        db.ForeignKey("coach_technical_observations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    coach_summary = db.Column(db.Text, nullable=False)
    action = db.Column(db.Text, nullable=False)
    follow_up_required = db.Column(db.Boolean, nullable=False, default=False)
    resolved = db.Column(db.Boolean, nullable=False, default=False)
    external_url = db.Column(db.String(2048), nullable=True)
    created_at = db.Column(
        db.DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    athlete = db.relationship("Athlete", backref="external_coaching_reviews")
    session_log = db.relationship("TrainingSessionLog")
    set_result = db.relationship("TrainingSetResult")
    observation = db.relationship("CoachTechnicalObservation")
